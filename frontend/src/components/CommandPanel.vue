<script setup>
defineProps({
  error: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  modelValue: { type: String, default: '' },
  statusLabel: { type: String, required: true },
})

const emit = defineEmits(['update:modelValue', 'submit'])
</script>

<template>
  <section class="hero">
    <div class="hero-copy">
      <div class="brand-row">
        <span class="brand-mark"><Code2 :size="24" /></span>
        <span>project-helper</span>
      </div>
      <h1>源码学习工作台</h1>
      <p>创建分析任务后，沿着进度进入源码、报告和问答三个视图。</p>
    </div>
    <div class="command-panel">
      <div class="command-head">
        <label for="repo">GitHub 仓库地址</label>
        <span>{{ statusLabel }}</span>
      </div>
      <div class="repo-form">
        <input
          id="repo"
          :value="modelValue"
          placeholder="https://github.com/owner/repo"
          @input="emit('update:modelValue', $event.target.value)"
          @keydown.enter="emit('submit')"
        />
        <button :disabled="loading" @click="emit('submit')">
          <Loader2 v-if="loading" class="spin" :size="18" />
          <Play v-else :size="18" />
          <span>{{ loading ? '分析中' : '开始分析' }}</span>
        </button>
      </div>
      <div class="status-strip">
        <span><Database :size="16" /> SQLite 缓存</span>
        <span><TerminalSquare :size="16" /> SSE 实时进度</span>
        <span><Bot :size="16" /> LangChain Agent</span>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </section>
</template>
