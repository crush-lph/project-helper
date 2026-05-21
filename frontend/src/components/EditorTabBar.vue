<script setup>
defineProps({
  activeTab: { type: String, required: true },
  tabs: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'select'])
</script>

<template>
  <nav class="editor-tabs" aria-label="编辑器页签">
    <button
      v-for="tab in tabs"
      :key="tab.id"
      :class="['editor-tab', { active: activeTab === tab.id, permanent: tab.permanent }]"
      @click="emit('select', tab.id)"
    >
      <BookOpen v-if="tab.type === 'report'" :size="15" />
      <FileCode2 v-else :size="15" />
      <span>{{ tab.title }}</span>
      <button
        v-if="!tab.permanent"
        class="tab-close"
        type="button"
        title="关闭"
        aria-label="关闭页签"
        @click.stop="emit('close', tab.id)"
      >
        <X :size="14" />
      </button>
    </button>
  </nav>
</template>
