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
const activeNode = ref('')
const nodeLogs = ref([])

const renderedReport = computed(() => {
  if (!report.value) return ''
  return marked(report.value)
})

const canSubmit = computed(() => {
  return !loading.value && teamA.value.trim() && teamB.value.trim()
})

function pushLog(node, status, message) {
  nodeLogs.value.push({ node, status, message, time: new Date().toLocaleTimeString() })
}

// ===================== 核心函数 =====================
async function handleAnalyze() {
  if (!canSubmit.value) return

  loading.value = true
  errorMsg.value = ''
  report.value = ''
  fetchErrors.value = 0
  activeNode.value = ''
  nodeLogs.value = []

  try {
    const resp = await fetch('/api/analyze/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team_a: teamA.value.trim(), team_b: teamB.value.trim() }),
    })

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // 保留不完整的行

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.node === 'done') {
            report.value = event.final_report || ''
            loading.value = false
            activeNode.value = ''
          } else if (event.node === 'error') {
            errorMsg.value = event.message || '分析失败'
            loading.value = false
            activeNode.value = ''
          } else {
            activeNode.value = event.node
            pushLog(event.node, event.status, event.message || '')
          }
        } catch (_) {}
      }
    }

  } catch (e) {
    errorMsg.value = e.message || '网络请求失败'
    loading.value = false
    activeNode.value = ''
  }
}

const nodeLabels = {
  scout: '球探',
  retriever: '情报检索',
  analyst: '分析师',
  editor: '主编',
}
</script>

<template>
  <div class="min-h-screen bg-console-bg flex flex-col">

    <!-- 顶部导航栏 -->
    <header class="border-b border-console-border bg-console-panel px-6 py-3 flex items-center gap-3">
      <div class="w-2 h-2 rounded-full bg-console-green animate-pulse"></div>
      <span class="text-console-green text-sm font-semibold tracking-widest">FOOTBALL_ANALYSIS_SYSTEM</span>
      <span class="text-console-border">|</span>
      <span class="text-console-gray text-xs">Multi-Agent LangGraph Engine v3.0</span>
      <span v-if="fetchErrors > 0" class="ml-auto text-console-yellow text-xs">
        [WARN] fetch_errors={{ fetchErrors }}
      </span>
    </header>

    <!-- 主内容区：左中右三栏 -->
    <main class="flex-1 flex overflow-hidden">

      <!-- 左侧：表单面板 -->
      <aside class="w-72 border-r border-console-border flex flex-col bg-console-panel/50">

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
            </label>
            <input v-model="teamA" type="text" placeholder="e.g. 曼城" class="input-console" :disabled="loading" />
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
            </label>
            <input v-model="teamB" type="text" placeholder="e.g. 阿森纳" class="input-console" :disabled="loading" />
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMsg" class="text-console-red text-xs p-3 border border-console-red/30 rounded bg-console-red/5">
            <span class="font-bold">[ERROR]</span> {{ errorMsg }}
          </div>

          <button type="submit" :disabled="!canSubmit" :class="loading ? 'btn-loading' : 'btn-primary'" class="mt-auto">
            <span v-if="loading" class="flex items-center justify-center gap-2">
              <span class="w-3 h-3 border-2 border-console-yellow/30 border-t-console-yellow rounded-full animate-spin"></span>
              STREAMING...
            </span>
            <span v-else>[EXEC] 开始分析</span>
          </button>
        </form>

        <!-- 底部状态栏 -->
        <div class="px-5 py-3 border-t border-console-border text-xs text-console-gray/40 space-y-1">
          <div>api: /api/analyze/stream</div>
          <div>model: MiniMax-M2</div>
          <div>status: {{ loading ? 'RUNNING' : 'IDLE' }}</div>
        </div>
      </aside>

      <!-- 中间：节点运行状态面板 -->
      <aside class="w-64 border-r border-console-border flex flex-col bg-console-panel/30 overflow-hidden">
        <div class="px-4 py-3 border-b border-console-border">
          <span class="text-xs text-console-gray">// AGENT STATUS</span>
        </div>
        <div class="flex-1 overflow-auto p-4 space-y-3">
          <div
            v-for="node in ['scout', 'retriever', 'analyst', 'editor']"
            :key="node"
            :class="[
              'border rounded p-3 transition-all duration-300',
              activeNode === node
                ? 'border-console-blue bg-console-blue/10'
                : nodeLogs.find(l => l.node === node)
                ? 'border-console-green/40 bg-console-green/5'
                : 'border-console-border/40 bg-transparent'
            ]"
          >
            <div class="flex items-center gap-2">
              <div
                :class="[
                  'w-2 h-2 rounded-full',
                  activeNode === node ? 'bg-console-blue animate-pulse'
                    : nodeLogs.find(l => l.node === node) ? 'bg-console-green'
                    : 'bg-console-border'
                ]"
              ></div>
              <span class="text-xs font-semibold" :class="activeNode === node ? 'text-console-blue' : 'text-console-gray'">
                {{ nodeLabels[node] }}
              </span>
            </div>
            <div v-if="nodeLogs.find(l => l.node === node)" class="mt-2 text-xs text-console-gray/60">
              {{ nodeLogs.find(l => l.node === node).status }}
            </div>
          </div>
        </div>
      </aside>

      <!-- 右侧：报告展示面板 -->
      <section class="flex-1 flex flex-col overflow-hidden">

        <div class="px-6 py-3 border-b border-console-border bg-console-panel/30 flex items-center gap-2">
          <span class="text-xs text-console-gray">// OUTPUT</span>
          <span v-if="report" class="text-console-green text-xs">[OK] report generated</span>
          <span v-else class="text-console-gray/30 text-xs">[EMPTY] awaiting input</span>
        </div>

        <div class="flex-1 overflow-auto p-6">
          <div v-if="report" class="report-content" v-html="renderedReport"></div>

          <div v-else-if="loading" class="flex flex-col items-center justify-center h-full gap-4 text-console-gray/40">
            <div class="flex gap-1">
              <span v-for="i in 3" :key="i" class="w-2 h-2 rounded-full bg-console-blue/40 animate-bounce"
                    :style="{ animationDelay: `${i * 0.15}s` }"></span>
            </div>
            <p class="text-xs tracking-widest">
              {{ activeNode ? `RUNNING: ${nodeLabels[activeNode] || activeNode}` : 'INITIALIZING...' }}
            </p>
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