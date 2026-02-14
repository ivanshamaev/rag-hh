<template>
  <div class="layout">
    <header class="header">
      <router-link to="/" class="logo">
        <span class="logo-icon">RAG</span>
        <span class="logo-text">HH</span>
      </router-link>
      <nav class="nav">
        <router-link to="/" active-class="active" class="nav-link">Дашборд</router-link>
        <router-link to="/search" active-class="active" class="nav-link">Поиск</router-link>
        <router-link to="/rag" active-class="active" class="nav-link">RAG</router-link>
      </nav>
      <div v-if="apiStatus !== null" class="api-status" :class="apiStatus ? 'ok' : 'err'" :title="apiStatus ? 'API доступен' : 'API недоступен'">
        {{ apiStatus ? 'API ✓' : 'API ✗' }}
      </div>
    </header>
    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { health } from '@/api'

const apiStatus = ref(null)

onMounted(async () => {
  try {
    await health()
    apiStatus.value = true
  } catch {
    apiStatus.value = false
  }
})
</script>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  align-items: center;
  gap: 2rem;
  padding: 1rem 1.5rem;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 10;
}

.logo {
  display: flex;
  align-items: baseline;
  gap: 0.25rem;
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--text);
  text-decoration: none;
}
.logo:hover { text-decoration: none; color: var(--accent); }
.logo-icon { color: var(--accent); font-family: var(--font-mono); }
.logo-text { letter-spacing: 0.05em; }

.nav {
  display: flex;
  gap: 0.5rem;
}

.nav-link {
  padding: 0.5rem 1rem;
  border-radius: var(--radius);
  color: var(--text-muted);
  text-decoration: none;
  font-weight: 500;
  transition: color 0.15s, background 0.15s;
}
.nav-link:hover { color: var(--text); background: var(--bg-input); text-decoration: none; }
.nav-link.active { color: var(--accent); background: rgba(245, 158, 11, 0.12); }

.api-status {
  margin-left: auto;
  font-size: 0.8rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  font-family: var(--font-mono);
}
.api-status.ok { color: var(--success); background: rgba(52, 211, 153, 0.15); }
.api-status.err { color: #f87171; background: rgba(248, 113, 113, 0.15); }

.main {
  flex: 1;
  padding: 1.5rem;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
