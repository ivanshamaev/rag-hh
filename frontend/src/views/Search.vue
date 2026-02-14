<template>
  <div class="search-page">
    <h1 class="page-title">Семантический поиск</h1>
    <p class="page-desc">Поиск вакансий по смыслу запроса (векторное сходство)</p>

    <form class="search-form" @submit.prevent="runSearch">
      <input
        v-model="query"
        type="text"
        class="search-input"
        placeholder="Например: удалённая работа Python, Москва data engineer"
        autofocus
      />
      <div class="form-row">
        <label class="limit-label">
          Показать
          <select v-model.number="limit" class="limit-select">
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
          </select>
          результатов
        </label>
        <button type="submit" class="btn" :disabled="loading || !query.trim()">
          {{ loading ? 'Поиск…' : 'Искать' }}
        </button>
      </div>
    </form>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="results.length" class="results">
      <p class="results-meta">Найдено по запросу «{{ lastQuery }}»</p>
      <ul class="result-list">
        <li v-for="r in results" :key="r.hh_id" class="result-card">
          <div class="result-header">
            <a :href="r.url" target="_blank" rel="noopener" class="result-title">{{ r.name }}</a>
            <span class="similarity" :title="'Релевантность: ' + (r.similarity * 100).toFixed(1) + '%'">
              {{ (r.similarity * 100).toFixed(0) }}%
            </span>
          </div>
          <div class="result-meta">
            <span v-if="r.employer_name">{{ r.employer_name }}</span>
            <span v-if="r.area_name" class="muted"> · {{ r.area_name }}</span>
          </div>
          <div v-if="r.salary_from || r.salary_to" class="result-salary">
            {{ formatSalary(r.salary_from, r.salary_to) }}
          </div>
          <p v-if="r.description" class="result-desc">{{ r.description }}</p>
        </li>
      </ul>
    </div>
    <div v-else-if="searched && !loading" class="empty muted">Введите запрос и нажмите «Искать» или отправьте форму</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { search as apiSearch } from '@/api'

const query = ref('')
const limit = ref(10)
const loading = ref(false)
const error = ref(null)
const results = ref([])
const lastQuery = ref('')
const searched = ref(false)

function formatSalary(from, to) {
  const a = from != null ? from.toLocaleString('ru-RU') : ''
  const b = to != null ? to.toLocaleString('ru-RU') : ''
  if (a && b) return `${a} – ${b} ₽`
  if (a) return `от ${a} ₽`
  if (b) return `до ${b} ₽`
  return ''
}

async function runSearch() {
  const q = query.value.trim()
  if (!q) return
  loading.value = true
  error.value = null
  searched.value = true
  try {
    const data = await apiSearch(q, limit.value)
    results.value = data.results || []
    lastQuery.value = data.query || q
  } catch (e) {
    error.value = e.message
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.search-page { }
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
.results-meta { color: var(--text-muted); margin: 0 0 1rem 0; font-size: 0.9rem; }
.result-list { list-style: none; padding: 0; margin: 0; }
.result-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  margin-bottom: 0.75rem;
}
.result-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.75rem; }
.result-title { font-weight: 600; color: var(--text); text-decoration: none; flex: 1; }
.result-title:hover { color: var(--accent); text-decoration: underline; }
.similarity {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--accent);
  background: rgba(245, 158, 11, 0.15);
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  flex-shrink: 0;
}
.result-meta { font-size: 0.9rem; color: var(--text-muted); margin-top: 0.25rem; }
.result-salary { font-size: 0.9rem; margin-top: 0.25rem; color: var(--success); }
.result-desc { font-size: 0.9rem; color: var(--text-muted); margin: 0.5rem 0 0 0; line-height: 1.45; }
.empty { padding: 2rem; text-align: center; }
</style>
