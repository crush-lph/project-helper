<script setup>
defineProps({
  activeProjectId: { type: String, default: '' },
  busyProjectId: { type: String, default: '' },
  projects: { type: Array, default: () => [] },
})

const emit = defineEmits(['delete', 'load', 'toggle-pin'])
</script>

<template>
  <aside class="sidebar">
    <div class="panel-title">
      <FolderGit2 :size="18" />
      <span>已分析项目</span>
    </div>
    <div
      v-for="project in projects"
      :key="project.id"
      :class="['project-item', { active: activeProjectId === project.id, pinned: project.pinned }]"
    >
      <button class="project-load" :disabled="busyProjectId === project.id" @click="emit('load', project)">
        <span class="project-name-row">
          <Pin v-if="project.pinned" :size="14" />
          <strong>{{ project.name }}</strong>
        </span>
        <small>{{ project.status }} · {{ project.repo_url }}</small>
      </button>
      <div class="project-actions" aria-label="项目操作">
        <button
          class="icon-button"
          :title="project.pinned ? '取消置顶' : '置顶'"
          :aria-label="project.pinned ? '取消置顶' : '置顶'"
          :disabled="busyProjectId === project.id"
          @click="emit('toggle-pin', project)"
        >
          <PinOff v-if="project.pinned" :size="16" />
          <Pin v-else :size="16" />
        </button>
        <button
          class="icon-button danger"
          title="删除"
          aria-label="删除"
          :disabled="busyProjectId === project.id"
          @click="emit('delete', project)"
        >
          <Trash2 :size="16" />
        </button>
      </div>
    </div>
    <p v-if="!projects.length" class="muted">还没有缓存项目。</p>
  </aside>
</template>
