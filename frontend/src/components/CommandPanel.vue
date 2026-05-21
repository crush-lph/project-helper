<script setup>
defineProps({
  error: { type: String, default: "" },
  loading: { type: Boolean, default: false },
  modelValue: { type: String, default: "" },
  statusLabel: { type: String, required: true },
  user: { type: Object, default: null },
});

const emit = defineEmits(["logout", "update:modelValue", "submit"]);
</script>

<template>
  <section class="topbar">
    <div class="brand">
      <span class="brand-mark"><Code2 :size="22" /></span>
      <div>
        <strong>project-helper</strong>
        <span>源码学习工作台</span>
      </div>
    </div>
    <div class="command-panel">
      <label class="repo-label" for="repo">
        <GitBranch :size="18" />
        <span>
          GitHub 仓库地址
          <input
            id="repo"
            :value="modelValue"
            placeholder="https://github.com/owner/repo"
            @input="emit('update:modelValue', $event.target.value)"
            @keydown.enter="emit('submit')"
          />
        </span>
      </label>
      <button
        class="primary-action"
        :disabled="loading"
        @click="emit('submit')"
      >
        <Loader2 v-if="loading" class="spin" :size="18" />
        <Play v-else :size="18" />
        <span>{{ loading ? "分析中" : "开始分析" }}</span>
      </button>
    </div>
    <div class="top-actions" aria-label="工作台状态">
      <span v-if="user" class="tool-chip user-chip"
        ><User :size="16" />{{ user.username }}</span
      >
      <button class="panel-action logout-action" @click="emit('logout')">
        退出
      </button>
      <span class="status-badge">{{ statusLabel }}</span>
    </div>
    <p v-if="error" class="error topbar-error">{{ error }}</p>
  </section>
</template>
