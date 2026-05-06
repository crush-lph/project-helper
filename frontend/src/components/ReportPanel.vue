<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '../helpers/markdown'

const props = defineProps({
  project: { type: Object, default: null },
})

const reportHtml = computed(() => renderMarkdown(props.project?.report || ''))
</script>

<template>
  <article class="report-panel">
    <div class="panel-title">
      <BookOpen :size="18" />
      <span>源码分析报告</span>
    </div>
    <div v-if="project?.report" class="markdown-body" v-html="reportHtml"></div>
    <div v-else class="empty-state">
      <Search :size="42" />
      <h2>等待一份源码地图</h2>
      <p>报告会覆盖项目概述、技术栈、目录结构、核心模块、数据流、设计模式和阅读路线。</p>
    </div>
  </article>
</template>
