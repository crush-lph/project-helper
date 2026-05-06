<script setup>
defineProps({
  activeView: { type: String, required: true },
  tabs: { type: Array, required: true },
})

const emit = defineEmits(['select'])
</script>

<template>
  <nav class="view-switcher" aria-label="工作区视图">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      :class="['view-tab', { active: activeView === tab.key }]"
      :disabled="tab.disabled"
      :aria-current="activeView === tab.key ? 'page' : undefined"
      @click="emit('select', tab.key)"
    >
      <FolderOpen v-if="tab.key === 'source'" :size="16" />
      <BookOpen v-else-if="tab.key === 'report'" :size="16" />
      <MessageSquareText v-else :size="16" />
      <span>{{ tab.label }}</span>
    </button>
  </nav>
</template>
