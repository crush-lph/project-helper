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

  await page.route('**/api/projects/project-1/chat/stream', async (route) => {
    await route.fulfill({
      contentType: 'text/event-stream',
      body: 'event: token\ndata: {"text":"可以从 src/main.js 开始阅读。"}\n\nevent: done\ndata: {}\n\n',
    })
  })
}

test.beforeEach(async ({ page }) => {
  await installApiMocks(page)
})

test('loads a cached project, browses source, and highlights code', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('button', { name: /demo-repo/ }).click()
  await expect(page.getByRole('button', { name: '折叠 src' })).toBeVisible()

  await page.getByRole('button', { name: '查看 src/main.js' }).click()

  await expect(page.getByText('src/main.js')).toBeVisible()
  await expect(page.locator('.source-code .hljs-keyword').first()).toHaveText('export')
})

test('switches between source, report, and chat workflows', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /demo-repo/ }).click()

  await page.getByRole('button', { name: '报告' }).click()
  await expect(page.getByRole('heading', { name: 'Demo report' })).toBeVisible()

  await page.getByRole('button', { name: '问答' }).click()
  await page.getByRole('textbox').last().fill('从哪里开始读？')
  await page.getByRole('button', { name: '提问' }).click()

  await expect(page.getByText('可以从 src/main.js 开始阅读。')).toBeVisible()
})
