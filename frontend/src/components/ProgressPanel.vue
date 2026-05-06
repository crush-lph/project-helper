<script setup>
defineProps({
  isCachedRun: { type: Boolean, default: false },
  latestProgress: { type: Object, default: null },
  pipelineSteps: { type: Array, required: true },
  progress: { type: Array, default: () => [] },
  progressLog: { type: Array, default: () => [] },
  progressPercent: { type: Number, default: 8 },
  statusLabel: { type: String, required: true },
  stepState: { type: Function, required: true },
})
</script>

<template>
  <div class="progress-panel">
    <div class="metrics-row">
      <article class="metric">
        <div><span>当前状态</span><RadioTower :size="18" /></div>
        <strong>{{ statusLabel }}</strong>
        <small>{{ latestProgress?.message || '等待任务开始' }}</small>
      </article>
      <article class="metric">
        <div><span>事件数量</span><Activity :size="18" /></div>
        <strong>{{ progress.length }}</strong>
        <small>{{ isCachedRun ? '缓存命中' : 'SSE 实时输出' }}</small>
      </article>
      <article class="metric">
        <div><span>完成进度</span><DatabaseZap :size="18" /></div>
        <strong>{{ Math.round(progressPercent) }}%</strong>
        <small>clone / scan / report / cache</small>
      </article>
    </div>

    <section class="flow-panel">
      <div class="flow-head">
        <div class="panel-title inline-title">
          <RadioTower :size="20" />
          <span>分析流程</span>
        </div>
        <span class="status-badge compact"><Activity :size="16" />SSE 实时输出</span>
      </div>
      <div class="flow-track" aria-label="分析流程">
        <article v-for="step in pipelineSteps.slice(1)" :key="step.key" :class="['flow-step', stepState(step.key)]">
          <span class="flow-node">
            <GitPullRequestArrow v-if="step.key === 'clone'" :size="18" />
            <ScanSearch v-else-if="step.key === 'scan'" :size="18" />
            <BookOpenCheck v-else-if="step.key === 'summarize'" :size="18" />
            <DatabaseZap v-else :size="18" />
          </span>
          <strong>{{ step.label }}</strong>
          <small>{{ step.hint }}</small>
        </article>
      </div>
    </section>

    <div v-if="progress.length" class="event-stream">
      <div class="stream-head">
        <span>{{ isCachedRun ? '缓存命中' : '实时输出' }}</span>
        <small>{{ progress.length }} 条事件</small>
      </div>
      <div class="stream-list">
        <div v-for="(item, index) in progressLog" :key="`${item.step}-${index}`" :class="['stream-item', item.step]">
          <span class="stream-badge">{{ item.step }}</span>
          <span>{{ item.message }}</span>
        </div>
      </div>
    </div>
    <div v-else class="step quiet">
      <Sparkles :size="17" />
      <span>输入仓库地址后，克隆、扫描、生成报告的实时状态会显示在这里。</span>
    </div>
  </div>
</template>
