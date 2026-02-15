<template>
  <div class="dashboard">
    <h1 class="page-title">Дашборд</h1>
    <p class="page-desc">Статистика по индексированным вакансиям из hh.ru</p>

    <div v-if="loading" class="loading">Загрузка…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else>
      <div class="cards">
        <div class="card">
          <span class="card-value">{{ stats.total_vacancies.toLocaleString('ru') }}</span>
          <span class="card-label">Вакансий в индексе</span>
        </div>
        <div class="card">
          <span class="card-value">{{ stats.unique_employers.toLocaleString('ru') }}</span>
          <span class="card-label">Компаний</span>
        </div>
        <div class="card">
          <span class="card-value">{{ stats.vacancies_with_salary.toLocaleString('ru') }}</span>
          <span class="card-label">С указанной зарплатой</span>
        </div>
        <div class="card highlight" v-if="stats.avg_salary_from != null">
          <span class="card-value">{{ formatSalary(stats.avg_salary_from) }} – {{ formatSalary(stats.avg_salary_to) }}</span>
          <span class="card-label">Средняя вилка (руб)</span>
        </div>
        <div class="card" v-if="stats.raw_vacancies_count != null">
          <span class="card-value">{{ stats.raw_vacancies_count.toLocaleString('ru') }}</span>
          <span class="card-label">В сыром виде (raw), ждут эмбеддингов</span>
        </div>
      </div>

      <section class="section">
        <h2 class="section-title">Топ регионов по вакансиям</h2>
        <div v-if="!stats.top_areas?.length" class="muted">Нет данных</div>
        <ul class="area-list" v-else>
          <li v-for="a in stats.top_areas" :key="a.name" class="area-row">
            <span class="area-name">{{ a.name }}</span>
            <span class="area-count">{{ a.count }}</span>
            <div class="area-bar" :style="{ width: barWidth(a.count) + '%' }"></div>
          </li>
        </ul>
      </section>

      <section class="section tips">
        <h2 class="section-title">Что можно сделать</h2>
        <ul class="tips-list">
          <li><router-link to="/search">Поиск</router-link> — семантический поиск по вакансиям (по смыслу, не по ключевым словам).</li>
          <li><router-link to="/rag">RAG</router-link> — запрос контекста (топ вакансий) для передачи в LLM или анализа.</li>
          <li>Два этапа: выгрузка в raw (<code>POST /ingest</code>, <code>POST /ingest/bulk</code>), затем эмбеддинги в RAG (<code>POST /ingest/embed</code>).</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getStats } from '@/api'

const loading = ref(true)
const error = ref(null)
const stats = ref({
  total_vacancies: 0,
  unique_employers: 0,
  top_areas: [],
  vacancies_with_salary: 0,
  avg_salary_from: null,
  avg_salary_to: null,
  raw_vacancies_count: null,
})

function formatSalary(n) {
  if (n == null) return '—'
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(n)
}

function barWidth(count) {
  const max = Math.max(...(stats.value.top_areas || []).map((a) => a.count), 1)
  return Math.round((count / max) * 100)
}

onMounted(async () => {
  try {
    stats.value = await getStats()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dashboard { }
.page-title { font-size: 1.75rem; font-weight: 700; margin: 0 0 0.25rem 0; }
.page-desc { color: var(--text-muted); margin: 0 0 1.5rem 0; }

.loading, .error { padding: 2rem; text-align: center; }
.error { color: #f87171; }

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  position: relative;
  overflow: hidden;
}
.card.highlight { border-color: rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.06); }
.card-value { display: block; font-size: 1.5rem; font-weight: 700; font-family: var(--font-mono); color: var(--accent); }
.card-label { font-size: 0.875rem; color: var(--text-muted); }

.section { margin-bottom: 2rem; }
.section-title { font-size: 1.1rem; font-weight: 600; margin: 0 0 1rem 0; }

.area-list { list-style: none; padding: 0; margin: 0; }
.area-row {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border);
}
.area-row:last-child { border-bottom: none; }
.area-name { z-index: 1; }
.area-count { font-family: var(--font-mono); color: var(--accent); font-weight: 500; z-index: 1; }
.area-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: rgba(245, 158, 11, 0.15);
  border-radius: 4px;
  max-width: 100%;
  transition: width 0.3s ease;
}

.tips { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.25rem; }
.tips-list { margin: 0; padding-left: 1.25rem; color: var(--text-muted); }
.tips-list li { margin-bottom: 0.5rem; }
.tips-list code { font-family: var(--font-mono); font-size: 0.85em; background: var(--bg-input); padding: 0.15rem 0.4rem; border-radius: 4px; }
</style>
