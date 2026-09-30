/* Preview uses integer cents; the server validates and saves the entire month. */
window.WalletBudget = (() => {
  function cents(raw) {
    let value = raw.trim().replace(/EUR/gi, "").replace(/[€\s\u00a0]/g, "");
    if (!value) return null;
    if (/^\+?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?$/.test(value)) {
      value = value.replaceAll(".", "").replace(",", ".");
    } else if (!/^\+?\d+(?:\.\d{1,2})?$/.test(value)) {
      throw new Error("Importo non valido");
    }
    const [integer, fraction = ""] = value.split(".");
    return BigInt(integer) * 100n + BigInt(fraction.padEnd(2, "0"));
  }
  function money(value) {
    const sign = value < 0n ? "−" : "";
    const amount = value < 0n ? -value : value;
    const integer = (amount / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return `${sign}${integer},${(amount % 100n).toString().padStart(2, "0")} €`;
  }
  function mode(group) {
    return group.querySelector('input[type="radio"]:checked')?.value === "sottocategorie";
  }
  function inputs(group) {
    return [...group.querySelectorAll(mode(group) ? "[data-budget-parts] input" : "[data-budget-manual] input")];
  }
  function signature(group) {
    return JSON.stringify([mode(group), inputs(group).map(input => [input.name, input.value])]);
  }
  function readLimit(input) {
    try {
      const value = cents(input.value);
      if (value !== null && value > 99999999999999n) throw new Error("Importo troppo grande");
      input.removeAttribute("aria-invalid");
      return {value, valid: true};
    } catch {
      input.setAttribute("aria-invalid", "true");
      return {value: null, valid: false};
    }
  }
  function balance(node, spent, limit, valid) {
    if (!node) return;
    let text = `${money(spent)} spesi`;
    if (!valid) text += " · Controlla gli importi";
    else if (limit !== null) {
      const remaining = limit - spent;
      text += ` · ${remaining < 0n ? "sforamento" : "residuo"} ${money(remaining < 0n ? -remaining : remaining)}`;
    }
    node.textContent = text;
  }
  function roundedPercent(spent, limit) {
    // Match Decimal's half-even rounding for the displayed whole percentage.
    const numerator = spent * 100n, whole = numerator / limit, remainder = numerator % limit;
    return whole + (2n * remainder > limit || (2n * remainder === limit && whole % 2n) ? 1n : 0n);
  }
  function progress(container, spent, limit, valid) {
    let state = "steady", width = 0, label = valid ? "Nessun limite" : "Controlla gli importi";
    if (valid && limit !== null) {
      state = spent > limit ? "over" : limit > 0n && spent * 100n >= limit * 85n ? "near" : "steady";
      const ratio = limit > 0n ? `${roundedPercent(spent, limit)}%` : "Limite zero";
      label = `${ratio} · ${state === "over" ? "Superato" : state === "near" ? "Vicino al limite" : "Regolare"}`;
      // Only the bounded visual width is converted to Number.
      width = limit > 0n ? (spent >= limit ? 100 : Number(spent * 10000n / limit) / 100) : spent > 0n ? 100 : 0;
    }
    const track = container.querySelector("[data-budget-progress]");
    track.classList.remove("steady", "near", "over");
    track.classList.add(state);
    track.querySelector("span").style.width = `${width}%`;
    container.querySelector("[data-budget-status]").textContent = label;
  }
  function preview(group) {
    const allocated = mode(group);
    const manual = group.querySelector("[data-budget-manual]");
    const parts = group.querySelector("[data-budget-parts]");
    manual.hidden = allocated;
    if (parts) parts.hidden = !allocated;
    manual.querySelectorAll("input").forEach(input => input.disabled = allocated);
    parts?.querySelectorAll("input").forEach(input => input.disabled = !allocated);
    const results = inputs(group).map(readLimit);
    const valid = results.every(result => result.valid);
    const amounts = results.filter(result => result.value !== null).map(result => result.value);
    const limit = valid && amounts.length ? amounts.reduce((sum, value) => sum + value, 0n) : null;
    const text = !valid ? "Controlla gli importi" : limit === null ? "Non impostato" : money(limit);
    group.querySelectorAll("[data-budget-total], [data-budget-parts-total]").forEach(output => output.textContent = text);
    group.querySelector("[data-budget-source]").textContent = allocated ? "Somma sottocategorie" : "Budget categoria";
    const spent = cents(group.dataset.budgetSpent) ?? 0n;
    balance(group.querySelector("[data-budget-balance]"), spent, limit, valid);
    progress(group.querySelector(".budget-summary"), spent, limit, valid);
    if (allocated) group.querySelectorAll("[data-budget-subcategory]").forEach(row => {
      const result = readLimit(row.querySelector("input"));
      const spent = cents(row.dataset.budgetSpent) ?? 0n;
      balance(row.querySelector("[data-budget-sub-balance]"), spent, result.value, result.valid);
      progress(row.querySelector(".budget-sub-progress"), spent, result.value, result.valid);
    });
    return {limit, valid};
  }
  function init(root = document) {
    const form = root.querySelector("[data-budget-form]");
    if (!form || form.dataset.ready) return;
    form.dataset.ready = "1";
    const groups = [...form.querySelectorAll("[data-budget-group]")];
    const initial = groups.map(signature);
    const kpis = root.querySelector("[data-budget-kpis]");
    const notice = form.querySelector("[data-budget-unsaved]");
    const update = () => {
      const results = groups.map(preview);
      const valid = results.every(result => result.valid);
      const total = results.reduce((sum, result) => sum + (result.limit ?? 0n), 0n);
      const spent = cents(kpis.dataset.budgetSpent) ?? 0n;
      const remaining = total - spent;
      const over = valid && remaining < 0n;
      kpis.querySelector("[data-budget-grand-total]").textContent = valid ? money(total) : "Da verificare";
      kpis.querySelector("[data-budget-remaining]").textContent = valid ? money(over ? -remaining : remaining) : "—";
      kpis.querySelector("[data-budget-remaining-label]").textContent = over ? "Sforamento" : "Residuo";
      kpis.querySelector("[data-budget-remaining-help]").textContent = !valid ? "Controlla gli importi" : over ? "Uscite oltre il budget" : "Budget − uscite";
      kpis.querySelector(".budget-residual").classList.toggle("is-over", over);
      notice.hidden = !form.querySelector(".alert-error") && groups.every((group, i) => signature(group) === initial[i]);
    };
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
  }
  return {init};
})();
