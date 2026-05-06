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
    <div class="metric">
      <span>当前状态</span>
      <strong>{{ statusLabel }}</strong>
      <small>{{ latestProgress?.message || '等待任务开始' }}</small>
    </div>
    <div class="progress-workbench">
      <div class="progress-track" aria-label="分析进度">
        <span :style="{ width: `${progressPercent}%` }"></span>
      </div>
      <div class="step-map">
        <div v-for="step in pipelineSteps" :key="step.key" :class="['stage', stepState(step.key)]">
          <span class="stage-dot">
            <CheckCircle2 v-if="stepState(step.key) === 'done'" :size="15" />
            <Loader2 v-else-if="stepState(step.key) === 'active'" class="spin" :size="15" />
            <span v-else></span>
          </span>
          <span class="stage-copy">
            <strong>{{ step.label }}</strong>
            <small>{{ step.hint }}</small>
          </span>
        </div>
      </div>
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
  </div>
</template>
