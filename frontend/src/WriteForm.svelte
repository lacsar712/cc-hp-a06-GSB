<script>
  export let terms = []
  export let onSave

  let herb = '白芍'
  let tempC = 110
  let minutes = 10
  let picked = []
  let error = ''
  let ok = ''

  function toggle(text) {
    picked = picked.includes(text) ? picked.filter((t) => t !== text) : [...picked, text]
  }

  async function submit() {
    error = ''
    ok = ''
    if (picked.length === 0) {
      error = '零点名拒写：开炒至少点名一项异物词条'
      return
    }
    const err = await onSave({
      herb,
      steps: [{ name: '清炒', temp_c: Number(tempC), minutes: Number(minutes) }],
      foreign_names: picked,
    })
    if (err) {
      error = err
    } else {
      ok = `已写入：${herb}，点名 ${picked.join('、')}`
      picked = []
    }
  }
</script>

<div class="write-form">
  <input bind:value={herb} placeholder="饮片" />
  <input type="number" bind:value={tempC} title="清炒温度" />
  <input type="number" bind:value={minutes} title="清炒时长（分钟）" />
  <div class="pick">
    <span>异物点名（至少一项）：</span>
    {#each terms as term}
      <label>
        <input
          type="checkbox"
          checked={picked.includes(term.text)}
          on:change={() => toggle(term.text)}
        />
        {term.text}
      </label>
    {/each}
    {#if terms.length === 0}<em>词条表为空，请先到词条维护添加</em>{/if}
  </div>
  <button on:click={submit}>写入清炒记录</button>
  {#if error}<p class="err">{error}</p>{/if}
  {#if ok}<p class="ok">{ok}</p>{/if}
</div>

<style>
  .write-form { border: 1px solid #d6c9b8; border-radius: 8px; padding: 12px; margin: 12px 0; }
  .pick { margin: 8px 0; }
  .pick label { margin-right: 12px; }
  .err { color: #b91c1c; }
  .ok { color: #15803d; }
  input { margin-right: 8px; padding: 6px; }
</style>
