<script>
  import { onMount } from 'svelte'

  let username = 'processor'
  let password = 'herb123456'
  let token = localStorage.getItem('herb_token') || ''
  let role = localStorage.getItem('herb_role') || ''
  let who = localStorage.getItem('herb_user') || ''
  let rows = []
  let terms = []
  let herb = '白芍'
  let tempC = 110
  let minutes = 10
  let named = []
  let error = ''
  let notice = ''
  let newTerm = ''
  let termError = ''
  let editingId = null
  let editingText = ''
  let view = 'home'

  function syncRoute() {
    view = location.hash === '#/terms' ? 'terms' : 'home'
  }

  onMount(() => {
    syncRoute()
    window.addEventListener('hashchange', syncRoute)
    return () => window.removeEventListener('hashchange', syncRoute)
  })

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || '请求失败')
    return data
  }

  async function enter() {
    const data = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    token = data.access_token
    role = data.role
    who = data.username
    localStorage.setItem('herb_token', token)
    localStorage.setItem('herb_role', role)
    localStorage.setItem('herb_user', who)
    await load()
  }

  async function load() {
    rows = await api('/api/batches')
    terms = await api('/api/terms')
  }

  async function save() {
    error = ''
    notice = ''
    try {
      await api('/api/batches', {
        method: 'POST',
        body: JSON.stringify({
          herb,
          steps: [{ name: '清炒', temp_c: Number(tempC), minutes: Number(minutes) }],
          foreign_named: named,
        }),
      })
      named = []
      notice = `已写入 ${herb} 的清炒记录`
      await load()
    } catch (err) {
      error = err.message
    }
  }

  async function addTerm() {
    termError = ''
    try {
      await api('/api/terms', { method: 'POST', body: JSON.stringify({ term: newTerm }) })
      newTerm = ''
      terms = await api('/api/terms')
    } catch (err) {
      termError = err.message
    }
  }

  function startEdit(term) {
    editingId = term.id
    editingText = term.term
    termError = ''
  }

  async function saveEdit() {
    termError = ''
    try {
      await api(`/api/terms/${editingId}`, { method: 'PUT', body: JSON.stringify({ term: editingText }) })
      editingId = null
      terms = await api('/api/terms')
    } catch (err) {
      termError = err.message
    }
  }

  async function removeTerm(term) {
    termError = ''
    try {
      await api(`/api/terms/${term.id}`, { method: 'DELETE' })
      named = named.filter((n) => n !== term.term)
      terms = await api('/api/terms')
    } catch (err) {
      termError = err.message
    }
  }

  function leave() {
    localStorage.clear()
    token = ''
    role = ''
    who = ''
  }

  function namedOf(row) {
    return (row.doc && row.doc.foreign_named) || []
  }

  $: namedRows = rows.filter((r) => namedOf(r).length > 0)

  if (token) load()
</script>

<main>
  {#if !token}
    <h1>饮片炮制记录台</h1>
    <p>炮制记录整包保存。清炒温度须在 80 到 150，时长须在 5 到 30 分钟。开炒前必须点名至少一项异物词条，点名原文随文书保存。</p>
    <input bind:value={username} />
    <input type="password" bind:value={password} />
    <button on:click={enter}>登录</button>
    <p>processor / herb123456 可写；checker / check123456 只读</p>
  {:else}
    <nav class="topbar">
      <strong>饮片炮制记录台</strong>
      <a href="#/" class:active={view === 'home'}>记录台</a>
      <a href="#/terms" class:active={view === 'terms'}>异物词条</a>
      <span class="spacer"></span>
      <span>{who} · {role === 'writer' ? '炮制员' : '质检员'}</span>
      <button on:click={leave}>退出</button>
    </nav>

    {#if view === 'home'}
      <h1>炮制文书</h1>
      <ul>
        {#each rows as row}
          <li>
            {row.herb} · {row.verdict} · {row.reason} · 温度 {row.doc.steps[0].temp_c}
            · 点名 {namedOf(row).length ? namedOf(row).join('、') : '未点名'}
          </li>
        {/each}
      </ul>
    {:else}
      <h1>异物词条</h1>

      <section>
        <h2>词条维护</h2>
        <ul>
          {#each terms as term}
            <li>
              {#if editingId === term.id}
                <input bind:value={editingText} />
                <button on:click={saveEdit}>保存</button>
                <button on:click={() => (editingId = null)}>取消</button>
              {:else}
                <span>{term.term}</span>
                {#if role === 'writer'}
                  <button on:click={() => startEdit(term)}>改名</button>
                  <button on:click={() => removeTerm(term)}>删除</button>
                {/if}
              {/if}
            </li>
          {/each}
        </ul>
        {#if role === 'writer'}
          <input bind:value={newTerm} placeholder="新词条" />
          <button on:click={addTerm}>添加词条</button>
        {:else}
          <p>质检员仅可查看词条，不能修改。</p>
        {/if}
        {#if termError}<p class="err">{termError}</p>{/if}
      </section>

      {#if role === 'writer'}
        <section>
          <h2>点名区</h2>
          <p>开炒至少点名一项异物词条，点名原文随文书保存，事后改词条表不影响已存点名。</p>
          <input bind:value={herb} placeholder="饮片" />
          <input type="number" bind:value={tempC} />
          <input type="number" bind:value={minutes} />
          <div>
            {#each terms as term}
              <label>
                <input type="checkbox" bind:group={named} value={term.term} />
                {term.term}
              </label>
            {/each}
          </div>
          <button on:click={save}>写入清炒记录</button>
          {#if error}<p class="err">{error}</p>{/if}
          {#if notice}<p class="ok">{notice}</p>{/if}
        </section>
      {/if}

      <section>
        <h2>已存点名一览</h2>
        {#if namedRows.length === 0}
          <p>暂无已存点名。</p>
        {:else}
          <ul>
            {#each namedRows as row}
              <li>#{row.id} {row.herb} · 点名 {namedOf(row).join('、')} · {row.verdict} · {row.created_by}</li>
            {/each}
          </ul>
        {/if}
      </section>
    {/if}
  {/if}
</main>

<style>
  main { font-family: sans-serif; max-width: 720px; margin: 24px auto; color: #3f2f1f; }
  h1 { color: #7c2d12; }
  h2 { color: #7c2d12; font-size: 1.1rem; }
  input { margin-right: 8px; padding: 6px; }
  label { margin-right: 12px; }
  section { border-top: 1px solid #d6c8b8; padding-top: 8px; margin-top: 16px; }
  .topbar { display: flex; align-items: center; gap: 16px; border-bottom: 2px solid #7c2d12; padding-bottom: 8px; }
  .topbar a { color: #7c2d12; text-decoration: none; }
  .topbar a.active { font-weight: bold; text-decoration: underline; }
  .spacer { flex: 1; }
  .err { color: #b91c1c; }
  .ok { color: #15803d; }
</style>
