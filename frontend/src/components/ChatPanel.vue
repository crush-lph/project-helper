<script setup>
import { renderMarkdown } from '../helpers/markdown'

defineProps({
  asking: { type: Boolean, default: false },
  isReady: { type: Boolean, default: false },
  messages: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['ask', 'update:modelValue'])
</script>

<template>
  <section class="chat-panel">
    <div class="panel-title">
      <MessageSquareText :size="18" />
      <span>源码问答</span>
    </div>
    <div class="chat-log">
      <div v-for="(message, index) in messages" :key="index" :class="['message', message.role]">
        <div v-if="message.role === 'assistant'" class="markdown-body compact" v-html="renderMarkdown(message.text || '思考中...')"></div>
        <p v-else>{{ message.text }}</p>
      </div>
      <p v-if="!messages.length" class="muted">报告生成后，可以问：“这个项目的启动流程是什么？”、“核心模块怎么协作？”</p>
    </div>
    <div class="ask-form">
      <input
        :value="modelValue"
        :disabled="!isReady || asking"
        @input="emit('update:modelValue', $event.target.value)"
        @keydown.enter="emit('ask')"
      />
      <button :disabled="!isReady || asking" @click="emit('ask')">
        <Loader2 v-if="asking" class="spin" :size="18" />
        <Bot v-else :size="18" />
        <span>{{ asking ? '回答中' : '提问' }}</span>
      </button>
    </div>
  </section>
</template>
