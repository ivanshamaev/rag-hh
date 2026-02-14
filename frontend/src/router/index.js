import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: 'Дашборд' } },
  { path: '/search', name: 'Search', component: () => import('@/views/Search.vue'), meta: { title: 'Поиск' } },
  { path: '/rag', name: 'Rag', component: () => import('@/views/Rag.vue'), meta: { title: 'RAG контекст' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} — RAG HH` : 'RAG HH'
})

export default router
