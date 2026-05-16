<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'

// ===================== 状态 =====================
const teamA = ref('')
const teamB = ref('')
const loading = ref(false)
const report = ref('')
const fetchErrors = ref(0)
const errorMsg = ref('')

// ===================== 计算属性 =====================
const renderedReport = computed(() => {
  if (!report.value) return ''
  return marked(report.value)
})

const canSubmit = computed(() => {
  return !loading.value && teamA.value.trim() && teamB.value.trim()
})

// ===================== 核心函数 =====================
async function handleAnalyze() {
  if (!canSubmit.value) return

  loading.value = true
  errorMsg.value = ''
  report.value = ''
  fetchErrors.value = 0

  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team_a: teamA.value.trim(), team_b: teamB.value.trim() }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '未知错误' }))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }

    const data = await resp.json()
    report.value = data.final_report || ''
    fetchErrors.value = data.fetch_errors || 0
  } catch (e) {
    errorMsg.value = e.message || '网络请求失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-console-bg flex flex-col">

    <!-- 顶部导航栏 -->
    <header class="border-b border-console-border bg-console-panel px-6 py-3 flex items-center gap-3">
      <div class="w-2 h-2 rounded-full bg-console-green animate-pulse"></div>
      <span class="text-console-green text-sm font-semibold tracking-widest">FOOTBALL_ANALYSIS_SYSTEM</span>
      <span class="text-console-border">|</span>
      <span class="text-console-gray text-xs">Multi-Agent LangGraph Engine v1.0</span>
      <span v-if="fetchErrors > 0" class="ml-auto text-console-yellow text-xs">
        [WARN] fetch_errors={{ fetchErrors }}
      </span>
    </header>

    <!-- 主内容区：左右分栏 -->
    <main class="flex-1 flex overflow-hidden">

      <!-- 左侧：表单面板 -->
      <aside class="w-80 border-r border-console-border flex flex-col bg-console-panel/50">

        <div class="p-5 border-b border-console-border">
          <h2 class="text-console-blue text-xs font-semibold tracking-widest mb-1">// MATCH INPUT</h2>
          <p class="text-console-gray/50 text-xs">输入两支球队名称，开始分析</p>
        </div>

        <form class="flex-1 p-5 flex flex-col gap-5" @submit.prevent="handleAnalyze">

          <!-- 主队输入 -->
          <div class="space-y-2">
            <label class="text-xs text-console-gray flex items-center gap-2">
              <span class="text-console-green">[A]</span>
              <span class="text-console-blue">team_a</span>
              <span class="text-console-gray/30">// home team</span>
            </label>
            <input
              v-model="teamA"
              type="text"
              placeholder="e.g. 曼城"
              class="input-console"
              :disabled="loading"
            />
          </div>

          <!-- VS 分隔 -->
          <div class="flex items-center gap-3">
            <div class="flex-1 h-px bg-console-border"></div>
            <span class="text-console-purple text-sm font-bold">VS</span>
            <div class="flex-1 h-px bg-console-border"></div>
          </div>

          <!-- 客队输入 -->
          <div class="space-y-2">
            <label class="text-xs text-console-gray flex items-center gap-2">
              <span class="text-console-red">[B]</span>
              <span class="text-console-blue">team_b</span>
              <span class="text-console-gray/30">// away team</span>
            </label>
            <input
              v-model="teamB"
              type="text"
              placeholder="e.g. 阿森纳"
              class="input-console"
              :disabled="loading"
            />
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMsg" class="text-console-red text-xs p-3 border border-console-red/30 rounded bg-console-red/5">
            <span class="font-bold">[ERROR]</span> {{ errorMsg }}
          </div>

          <!-- 提交按钮 -->
          <button
            type="submit"
            :disabled="!canSubmit"
            :class="loading ? 'btn-loading' : 'btn-primary'"
            class="mt-auto"
          >
            <span v-if="loading" class="flex items-center justify-center gap-2">
              <span class="w-3 h-3 border-2 border-console-yellow/30 border-t-console-yellow rounded-full animate-spin"></span>
              ANALYZING...
            </span>
            <span v-else>[EXEC] 开始分析</span>
          </button>
        </form>

        <!-- 底部状态栏 -->
        <div class="px-5 py-3 border-t border-console-border text-xs text-console-gray/40 space-y-1">
          <div>api: /api/analyze</div>
          <div>model: MiniMax-M2</div>
          <div>status: {{ loading ? 'RUNNING' : 'IDLE' }}</div>
        </div>
      </aside>

      <!-- 右侧：报告展示面板 -->
      <section class="flex-1 flex flex-col overflow-hidden">

        <!-- 面板头部 -->
        <div class="px-6 py-3 border-b border-console-border bg-console-panel/30 flex items-center gap-2">
          <span class="text-console-gray text-xs">// OUTPUT</span>
          <span v-if="report" class="text-console-green text-xs">[OK] report generated</span>
          <span v-else class="text-console-gray/30 text-xs">[EMPTY] awaiting input</span>
        </div>

        <!-- 报告正文 -->
        <div class="flex-1 overflow-auto p-6">
          <div v-if="report" class="report-content" v-html="renderedReport"></div>

          <div v-else-if="loading" class="flex flex-col items-center justify-center h-full gap-4 text-console-gray/40">
            <div class="flex gap-1">
              <span v-for="i in 3" :key="i" class="w-2 h-2 rounded-full bg-console-blue/40 animate-bounce"
                    :style="{ animationDelay: `${i * 0.15}s` }"></span>
            </div>
            <p class="text-xs tracking-widest">FETCHING DATA FROM API...</p>
          </div>

          <div v-else class="flex flex-col items-center justify-center h-full text-console-gray/30">
            <p class="text-6xl font-bold text-console-border mb-4">_</p>
            <p class="text-xs tracking-widest">AWAITING MATCH DATA</p>
            <p class="text-xs mt-2">fill in both team names and click [EXEC]</p>
          </div>
        </div>
      </section>

    </main>
  </div>
</template>