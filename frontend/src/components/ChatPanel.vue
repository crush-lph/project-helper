<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { renderMarkdown } from '../helpers/markdown'

const props = defineProps({
  asking: { type: Boolean, default: false },
  isReady: { type: Boolean, default: false },
  messages: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
  sourceTree: { type: Array, default: () => [] },
  referencedFiles: { type: Array, default: () => [] },
})

const chatLogRef = ref(null)

watch(() => props.messages.length, () => {
  nextTick(() => {
    if (chatLogRef.value) chatLogRef.value.scrollTop = chatLogRef.value.scrollHeight
  })
})

watch(() => props.messages.at(-1)?.text, () => {
  nextTick(() => {
    if (chatLogRef.value) chatLogRef.value.scrollTop = chatLogRef.value.scrollHeight
  })
})

const emit = defineEmits(['ask', 'stop', 'update:modelValue', 'update:referencedFiles'])

const inputRef = ref(null)
const showDropdown = ref(false)
const mentionQuery = ref('')
const dropdownIndex = ref(0)
let dropdownHandledEnter = false

const flatFiles = computed(() => {
  const files = []
  function walk(nodes) {
    for (const node of nodes) {
      if (node.type === 'file') files.push(node.path)
      if (node.children) walk(node.children)
    }
  }
  walk(props.sourceTree)
  return files
})

const filteredFiles = computed(() => {
  const query = mentionQuery.value.toLowerCase()
  const existing = new Set(props.referencedFiles)
  return flatFiles.value
    .filter((path) => !existing.has(path) && path.toLowerCase().includes(query))
    .slice(0, 12)
})

function onInput(e) {
  const value = e.target.value
  emit('update:modelValue', value)

  const cursor = e.target.selectionStart
  const before = value.slice(0, cursor)
  const atMatch = before.match(/@(\S*)$/)
  if (atMatch) {
    mentionQuery.value = atMatch[1]
    showDropdown.value = true
    dropdownIndex.value = 0
  } else {
    showDropdown.value = false
  }
}

function selectFile(path) {
  const input = inputRef.value
  if (!input) return
  const value = props.modelValue
  const cursor = input.selectionStart
  const before = value.slice(0, cursor)
  const after = value.slice(cursor)
  const newBefore = before.replace(/@\S*$/, '')
  emit('update:modelValue', newBefore + after)
  const files = [...props.referencedFiles, path]
  emit('update:referencedFiles', files)
  showDropdown.value = false
  nextTick(() => {
    input.focus()
    const pos = newBefore.length
    input.setSelectionRange(pos, pos)
  })
}

function removeFile(path) {
  emit('update:referencedFiles', props.referencedFiles.filter((f) => f !== path))
}

function onKeydown(e) {
  dropdownHandledEnter = false
  if (!showDropdown.value || !filteredFiles.value.length) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    dropdownIndex.value = (dropdownIndex.value + 1) % filteredFiles.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    dropdownIndex.value = (dropdownIndex.value - 1 + filteredFiles.value.length) % filteredFiles.value.length
  } else if (e.key === 'Escape') {
    e.preventDefault()
    showDropdown.value = false
  } else if (e.key === 'Enter') {
    e.preventDefault()
    selectFile(filteredFiles.value[dropdownIndex.value])
    dropdownHandledEnter = true
  }
}

function onSubmit() {
  if (dropdownHandledEnter) return
  if (!props.asking) {
    emit('ask')
    emit('update:modelValue', '')
  }
}
</script>

<template>
  <section class="chat-panel">
    <div class="panel-title">
      <MessageSquareText :size="18" />
      <span>源码问答</span>
    </div>
    <div ref="chatLogRef" class="chat-log">
      <div v-for="(message, index) in messages" :key="index" :class="['message', message.role]">
        <div v-if="message.role === 'assistant'" class="msg-avatar assistant-avatar"><Sparkles :size="14" /></div>
        <div class="msg-body">
          <div v-if="message.role === 'assistant'" class="markdown-body compact" v-html="renderMarkdown(message.text || '思考中...')"></div>
          <p v-else>{{ message.text }}</p>
        </div>
        <div v-if="message.role === 'user'" class="msg-avatar user-avatar"><User :size="14" /></div>
      </div>
      <p v-if="!messages.length" class="muted">报告生成后，可以问："这个项目的启动流程是什么？"、"核心模块怎么协作？"</p>
    </div>
    <div class="ask-form">
      <div v-if="referencedFiles.length" class="file-chips">
        <span v-for="path in referencedFiles" :key="path" class="file-chip">
          <FileCode2 :size="12" />
          <span class="chip-label">{{ path }}</span>
          <button class="chip-remove" @click="removeFile(path)" :disabled="asking">&times;</button>
        </span>
      </div>
      <div class="input-row">
        <div class="input-wrapper">
          <input
            ref="inputRef"
            :value="modelValue"
            :disabled="!isReady || asking"
            @input="onInput"
            @keydown="onKeydown"
            @keydown.enter="onSubmit"
            placeholder="输入问题，可用 @ 引用文件..."
          />
          <div v-if="showDropdown && filteredFiles.length" class="file-dropdown">
            <div
              v-for="(path, i) in filteredFiles"
              :key="path"
              :class="['dropdown-item', { active: i === dropdownIndex }]"
              @mousedown.prevent="selectFile(path)"
              @mouseenter="dropdownIndex = i"
            >
              <FileCode2 :size="14" />
              <span>{{ path }}</span>
            </div>
          </div>
        </div>
        <button
          :class="{ 'stop-answer': asking }"
          :disabled="!isReady"
          @click="asking ? emit('stop') : (emit('ask'), emit('update:modelValue', ''))"
        >
          <CircleStop v-if="asking" :size="18" />
          <Bot v-else :size="18" />
          <span>{{ asking ? '中止' : '提问' }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.msg-avatar {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}

.assistant-avatar {
  background: rgba(45, 212, 191, 0.15);
  color: var(--mint, #2dd4bf);
}

.user-avatar {
  background: rgba(134, 239, 172, 0.25);
  color: #16a34a;
}

.ask-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--accent-bg, #e8f0fe);
  color: var(--accent, #1a73e8);
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.4;
}

.chip-label {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-remove {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin: 0;
  color: inherit;
  font-size: 14px;
  line-height: 1;
  opacity: 0.6;
}

.chip-remove:hover {
  opacity: 1;
}

.input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.input-wrapper {
  position: relative;
}

.input-wrapper input {
  width: 100%;
}

.file-dropdown {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  max-height: 240px;
  overflow-y: auto;
  background: var(--panel, #1e293b);
  border: 1px solid var(--line, #334155);
  border-radius: 8px;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.25);
  z-index: 10;
  margin-bottom: 6px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 12px;
  color: var(--muted, #94a3b8);
}

.dropdown-item.active {
  background: rgba(45, 212, 191, 0.1);
  color: var(--mint, #2dd4bf);
}
</style>
