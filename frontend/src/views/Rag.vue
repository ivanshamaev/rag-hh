<template>
  <div class="rag-page">
    <h1 class="page-title">RAG — контекст для ответа</h1>
    <p class="page-desc">Получите топ релевантных вакансий в виде контекста (для передачи в LLM или анализа)</p>

    <form class="search-form" @submit.prevent="runRag">
      <input
        v-model="query"
        type="text"
        class="search-input"
        placeholder="Например: Какие вакансии по Data Engineer с удалёнкой?"
        autofocus
      />
      <div class="form-row">
        <label class="limit-label">
          Вакансий в контексте
          <select v-model.number="limit" class="limit-select">
            <option :value="3">3</option>
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="20">20</option>
          </select>
        </label>
        <button type="submit" class="btn" :disabled="loading || !query.trim()">
          {{ loading ? 'Загрузка…' : 'Получить контекст' }}
        </button>
      </div>
    </form>

    <div v-if="error" class="error">{{ error }}</div>
    <template v-else-if="ragResult">
      <section class="section">
        <h2 class="section-title">Источники (вакансии)</h2>
        <ul class="sources-list">
          <li v-for="(s, i) in ragResult.sources" :key="i" class="source-item">
            <a :href="s.url" target="_blank" rel="noopener" class="source-link">{{ s.name }}</a>
            <span class="source-sim">{{ (s.similarity * 100).toFixed(0) }}%</span>
          </li>
        </ul>
      </section>
      <section class="section context-section">
        <h2 class="section-title">
          Текст контекста
          <button type="button" class="copy-btn" @click="copyContext" title="Копировать">
            {{ copied ? 'Скопировано' : 'Копировать' }}
          </button>
        </h2>
        <pre class="context-block">{{ ragResult.context }}</pre>
      </section>
    </template>
    <div v-else-if="searched && !loading" class="empty muted">Введите вопрос и нажмите «Получить контекст»</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { rag as apiRag } from '@/api'

const query = ref('')
const limit = ref(5)
const loading = ref(false)
const error = ref(null)
const ragResult = ref(null)
const searched = ref(false)
const copied = ref(false)

async function runRag() {
  const q = query.value.trim()
  if (!q) return
  loading.value = true
  error.value = null
  ragResult.value = null
  searched.value = true
  try {
    ragResult.value = await apiRag(q, limit.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function copyContext() {
  if (!ragResult.value?.context) return
  try {
    await navigator.clipboard.writeText(ragResult.value.context)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}
</script>

<style scoped>
.rag-page { }
.page-title { font-size: 1.75rem; font-weight: 700; margin: 0 0 0.25rem 0; }
.page-desc { color: var(--text-muted); margin: 0 0 1.5rem 0; }

.search-form { margin-bottom: 1.5rem; }
.search-input {
  width: 100%;
  padding: 0.75rem 1rem;
  font-size: 1rem;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  margin-bottom: 0.75rem;
}
.search-input::placeholder { color: var(--text-muted); }
.search-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
}

.form-row { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
.limit-label { color: var(--text-muted); font-size: 0.9rem; display: flex; align-items: center; gap: 0.5rem; }
.limit-select {
  padding: 0.35rem 0.5rem;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
}
.btn {
  padding: 0.5rem 1.25rem;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: var(--radius);
  font-weight: 600;
  transition: background 0.15s;
}
.btn:hover:not(:disabled) { background: var(--accent-hover); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

.error { color: #f87171; margin-bottom: 1rem; }

.section { margin-bottom: 1.5rem; }
.section-title {
  font-size: 1rem; font-weight: 600; margin: 0 0 0.75rem 0;
  display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;
}
.copy-btn {
  font-size: 0.8rem;
  padding: 0.25rem 0.5rem;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-muted);
  transition: color 0.15s, border-color 0.15s;
}
.copy-btn:hover { color: var(--accent); border-color: var(--accent); }

.sources-list { list-style: none; padding: 0; margin: 0; }
.source-item {
  display: flex; align-items: center; justify-content: space-between; gap: 0.75rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--border);
}
.source-item:last-child { border-bottom: none; }
.source-link { flex: 1; }
.source-sim { font-family: var(--font-mono); font-size: 0.85rem; color: var(--accent); }

.context-section { }
.context-block {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.empty { padding: 2rem; text-align: center; }
</style>
