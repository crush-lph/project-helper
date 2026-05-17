<script setup>
const props = defineProps({
  error: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  mode: { type: String, default: 'login' },
  password: { type: String, default: '' },
  username: { type: String, default: '' },
})

const emit = defineEmits(['submit', 'update:mode', 'update:password', 'update:username'])

function submit() {
  emit('submit', props.mode)
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-panel">
      <div class="brand auth-brand">
        <span class="brand-mark"><User :size="22" /></span>
        <div>
          <strong>project-helper</strong>
          <span>登录后进入源码学习工作台</span>
        </div>
      </div>

      <div class="auth-tabs" aria-label="认证方式">
        <button :class="{ active: mode === 'login' }" @click="emit('update:mode', 'login')">登录</button>
        <button :class="{ active: mode === 'register' }" @click="emit('update:mode', 'register')">注册</button>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label>
          <span>用户名</span>
          <input
            autocomplete="username"
            :value="username"
            placeholder="alice"
            @input="emit('update:username', $event.target.value)"
          />
        </label>
        <label>
          <span>密码</span>
          <input
            autocomplete="current-password"
            :value="password"
            placeholder="至少 6 位"
            type="password"
            @input="emit('update:password', $event.target.value)"
          />
        </label>
        <button class="primary-action auth-submit" :disabled="loading" type="submit">
          <Loader2 v-if="loading" class="spin" :size="18" />
          <User v-else :size="18" />
          <span>{{ mode === 'register' ? '创建账号' : '登录' }}</span>
        </button>
      </form>

      <p v-if="error" class="error auth-error">{{ error }}</p>
    </section>
  </main>
</template>
