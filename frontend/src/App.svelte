<script>
  import { onMount } from 'svelte'
  import WriteForm from './WriteForm.svelte'

  let username = 'processor'
  let password = 'herb123456'
  let token = localStorage.getItem('herb_token') || ''
  let role = localStorage.getItem('herb_role') || ''
  let rows = []
  let terms = []
  let newTerm = ''
  let termError = ''
  let loginError = ''
  let route = location.hash || '#/'

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
    if (res.status === 204) return null
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || '请求失败')
    return data
  }

  async function enter() {
    loginError = ''
    try {
      const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      token = data.access_token
      role = data.role
      localStorage.setItem('herb_token', token)
      localStorage.setItem('herb_role', role)
      await load()
    } catch (err) {
      loginError = err.message
    }
  }

  async function load() {
    rows = await api('/api/batches')
    terms = await api('/api/foreign-terms')
  }

  // 写入文书：body.foreign_names 为点名原文，整包进文书；返回错误串或空串
  async function saveBatch(body) {
    try {
      await api('/api/batches', { method: 'POST', body: JSON.stringify(body) })
      await load()
      return ''
    } catch (err) {
      return err.message
    }
  }

  async function addTerm() {
    termError = ''
    const text = newTerm.trim()
    if (!text) return
    try {
      await api('/api/foreign-terms', { method: 'POST', body: JSON.stringify({ text }) })
      newTerm = ''
      terms = await api('/api/foreign-terms')
    } catch (err) {
      termError = err.message
    }
  }

  async function removeTerm(id) {
    termError = ''
    try {
      await api(`/api/foreign-terms/${id}`, { method: 'DELETE' })
      terms = await api('/api/foreign-terms')
    } catch (err) {
      termError = err.message
    }
  }

  function leave() {
    localStorage.clear()
    token = ''
    role = ''
  }

  function foreignNames(row) {
    return (row.doc && row.doc.foreign_names) || []
  }

  onMount(() => {
    const onHash = () => (route = location.hash || '#/')
    window.addEventListener('hashchange', onHash)
    if (token) load()
    return () => window.removeEventListener('hashchange', onHash)
  })
</script>

<main>
  {#if !token}
    <h1>饮片炮制记录台</h1>
    <p>炮制记录整包保存。清炒温度须在 80 到 150，时长须在 5 到 30 分钟。开炒必须点名异物词条。</p>
    <input bind:value={username} />
    <input type="password" bind:value={password} />
    <button on:click={enter}>登录</button>
    {#if loginError}<p class="err">{loginError}</p>{/if}
    <p>processor / herb123456 可写；checker / check123456 只读</p>
  {:else}
    <nav class="topbar">
      <strong>饮片炮制记录台</strong>
      <a href="#/" class:active={route !== '#/foreign-terms'}>炮制记录</a>
      <a href="#/foreign-terms" class:active={route === '#/foreign-terms'}>异物词条</a>
      <span class="spacer"></span>
      <span>{username}（{role === 'writer' ? '炮制员' : '质检员'}）</span>
      <button on:click={leave}>退出</button>
    </nav>

    {#if route === '#/foreign-terms'}
      <h1>异物词条</h1>

      <section>
        <h2>词条维护</h2>
        <ul>
          {#each terms as term}
            <li>
              {term.text}
              {#if role === 'writer'}
                <button class="link" on:click={() => removeTerm(term.id)}>删除</button>
              {/if}
            </li>
          {/each}
        </ul>
        {#if role === 'writer'}
          <input bind:value={newTerm} placeholder="新词条，如：金属屑" />
          <button on:click={addTerm}>添加词条</button>
        {:else}
          <p class="hint">质检员仅可查看词条，不能维护。</p>
        {/if}
        {#if termError}<p class="err">{termError}</p>{/if}
      </section>

      {#if role === 'writer'}
        <section>
          <h2>点名区</h2>
          <p class="hint">开炒至少点名一项词条，点名原文随文书整包保存。</p>
          <WriteForm {terms} onSave={saveBatch} />
        </section>
      {/if}

      <section>
        <h2>已存点名一览</h2>
        <ul>
          {#each rows.filter((r) => foreignNames(r).length > 0) as row}
            <li>{row.herb} · 点名：{foreignNames(row).join('、')} · {row.verdict} · {row.created_by}</li>
          {:else}
            <li>暂无已存点名</li>
          {/each}
        </ul>
        <p class="hint">点名原文已随文书存档，事后改动词条表不影响这里的内容。</p>
      </section>
    {:else}
      <h1>炮制记录</h1>
      {#if role === 'writer'}
        <WriteForm {terms} onSave={saveBatch} />
      {/if}
      <ul>
        {#each rows as row}
          <li>
            {row.herb} · {row.verdict} · {row.reason} · 温度 {row.doc.steps[0].temp_c}
            {#if foreignNames(row).length > 0} · 点名：{foreignNames(row).join('、')}{/if}
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</main>

<style>
  main { font-family: sans-serif; max-width: 720px; margin: 24px auto; color: #3f2f1f; }
  h1 { color: #7c2d12; }
  h2 { color: #7c2d12; font-size: 18px; }
  input { margin-right: 8px; padding: 6px; }
  section { border-top: 1px solid #e5dccb; padding-top: 8px; margin-top: 16px; }
  .topbar { display: flex; align-items: center; gap: 16px; background: #7c2d12; color: #fff; padding: 10px 16px; border-radius: 8px; }
  .topbar a { color: #f5d9c6; text-decoration: none; }
  .topbar a.active { color: #fff; font-weight: bold; text-decoration: underline; }
  .topbar .spacer { flex: 1; }
  .hint { color: #8a7a68; font-size: 13px; }
  .err { color: #b91c1c; }
  button.link { background: none; border: none; color: #b91c1c; cursor: pointer; text-decoration: underline; padding: 0 4px; }
</style>
