import { expect, test } from '@playwright/test'

const readyProject = {
  id: 'project-1',
  name: 'demo-repo',
  repo_url: 'https://github.com/example/demo-repo',
  status: 'ready',
  report: '# Demo report\n\n核心模块已经完成分析。',
  pinned: true,
}

const sourceTree = [
  {
    type: 'directory',
    name: 'src',
    path: 'src',
    children: [
      { type: 'file', name: 'main.js', path: 'src/main.js', size: 48 },
      { type: 'file', name: 'helper.ts', path: 'src/helper.ts', size: 32 },
    ],
  },
  { type: 'file', name: 'README.md', path: 'README.md', size: 18 },
]

async function installApiMocks(page) {
  let annotations = []

  await page.route('**/api/auth/login', async (route) => {
    await route.fulfill({
      json: { user: { id: 'user-1', username: 'tester' }, token: 'test-token' },
    })
  })

  await page.route('**/api/auth/register', async (route) => {
    await route.fulfill({
      json: { user: { id: 'user-1', username: 'tester' }, token: 'test-token' },
    })
  })

  await page.route('**/api/projects', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: { projects: [readyProject] } })
      return
    }
    await route.fulfill({ status: 201, json: readyProject })
  })

  await page.route('**/api/projects/project-1', async (route) => {
    await route.fulfill({ json: readyProject })
  })

  await page.route('**/api/projects/project-1/source/tree', async (route) => {
    await route.fulfill({ json: { tree: sourceTree } })
  })

  await page.route('**/api/projects/project-1/source/file?path=src%2Fmain.js', async (route) => {
    await route.fulfill({
      json: {
        path: 'src/main.js',
        content: 'export function greet(name) {\\n  return `hello ${name}`\\n}\\n',
        size: 56,
        truncated: false,
      },
    })
  })

  await page.route('**/api/projects/project-1/source/annotations**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET') {
      await route.fulfill({ json: { annotations: annotations.filter((item) => item.path === url.searchParams.get('path')) } })
      return
    }
    if (request.method() === 'POST') {
      const payload = request.postDataJSON()
      const created = {
        id: `note-${annotations.length + 1}`,
        project_id: 'project-1',
        path: payload.path,
        line: payload.line ?? null,
        body: payload.body,
        created_at: String(Date.now()),
        updated_at: String(Date.now()),
      }
      annotations = [...annotations, created]
      await route.fulfill({ json: created })
      return
    }
    if (request.method() === 'PATCH') {
      const id = url.pathname.split('/').pop()
      const payload = request.postDataJSON()
      annotations = annotations.map((item) => (item.id === id ? { ...item, body: payload.body, updated_at: String(Date.now()) } : item))
      await route.fulfill({ json: annotations.find((item) => item.id === id) })
      return
    }
    if (request.method() === 'DELETE') {
      const id = url.pathname.split('/').pop()
      annotations = annotations.filter((item) => item.id !== id)
      await route.fulfill({ status: 204 })
      return
    }
    await route.fulfill({ status: 405 })
  })

  await page.route('**/api/projects/project-1/chat/stream', async (route) => {
    await route.fulfill({
      contentType: 'text/event-stream',
      body: 'event: token\ndata: {"text":"可以从 src/main.js 开始阅读。"}\n\nevent: done\ndata: {}\n\n',
    })
  })
}

async function login(page) {
  await page.getByPlaceholder('alice').fill('tester')
  await page.getByPlaceholder('至少 6 位').fill('password123')
  await page.locator('form').getByRole('button', { name: '登录' }).click()
  await expect(page.getByRole('button', { name: /demo-repo/ })).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await installApiMocks(page)
})

test('loads a cached project, browses source, and highlights code', async ({ page }) => {
  await page.goto('/')
  await login(page)

  await page.getByRole('button', { name: /demo-repo/ }).click()
  await expect(page.getByRole('button', { name: '折叠 src' })).toBeVisible()

  await page.getByRole('button', { name: '查看 src/main.js' }).click()

  await expect(page.getByText('src/main.js')).toBeVisible()
  await expect(page.locator('.source-code .hljs-keyword').first()).toHaveText('export')
})

test('creates, edits, and deletes a source annotation', async ({ page }) => {
  await page.goto('/')
  await login(page)
  await page.getByRole('button', { name: /demo-repo/ }).click()
  await page.getByRole('button', { name: '查看 src/main.js' }).click()

  await page.getByRole('button', { name: '给第 1 行添加批注' }).click()
  await page.getByPlaceholder('写下这段源码的理解、问题或待验证点').fill('这是入口导出函数')
  await page.getByRole('button', { name: '添加', exact: true }).click()

  await expect(page.getByText('这是入口导出函数')).toBeVisible()
  await expect(page.getByRole('button', { name: '查看或新增第 1 行批注' })).toBeVisible()

  await page.locator('.annotation-actions').getByRole('button', { name: '编辑' }).click()
  await page.getByPlaceholder('写下这段源码的理解、问题或待验证点').fill('入口函数需要优先阅读')
  await page.getByRole('button', { name: '保存', exact: true }).click()

  await expect(page.getByText('入口函数需要优先阅读')).toBeVisible()

  await page.locator('.annotation-actions').getByRole('button', { name: '删除' }).click()

  await expect(page.getByText('入口函数需要优先阅读')).not.toBeVisible()
  await expect(page.getByText('还没有批注，可以从源码行旁添加。')).toBeVisible()
})

test('switches between source, report, and chat workflows', async ({ page }) => {
  await page.goto('/')
  await login(page)
  await page.getByRole('button', { name: /demo-repo/ }).click()

  await page.getByRole('button', { name: '报告' }).click()
  await expect(page.getByRole('heading', { name: 'Demo report' })).toBeVisible()

  await page.getByRole('button', { name: '问答' }).click()
  await page.getByRole('textbox').last().fill('从哪里开始读？')
  await page.getByRole('button', { name: '提问' }).click()

  await expect(page.getByText('可以从 src/main.js 开始阅读。')).toBeVisible()
})

test('stops an in-flight chat answer', async ({ page }) => {
  let releaseChat
  const chatReleased = new Promise((resolve) => {
    releaseChat = resolve
  })
  await page.route('**/api/projects/project-1/chat/stream', async (route) => {
    await chatReleased
    await route.abort('aborted').catch(() => {})
  })

  await page.goto('/')
  await login(page)
  await page.getByRole('button', { name: /demo-repo/ }).click()
  await page.getByRole('button', { name: '问答' }).click()
  await page.getByRole('textbox').last().fill('请解释架构')
  await page.getByRole('button', { name: '提问' }).click()

  await expect(page.getByRole('button', { name: '中止' })).toBeVisible()
  await page.getByRole('button', { name: '中止' }).click()
  releaseChat()

  await expect(page.getByText('已中止回答。')).toBeVisible()
  await expect(page.getByRole('button', { name: '提问' })).toBeVisible()
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})
