window.WalletFilters = (() => {
  let pending, timer;
  const qs = (selector) => document.querySelector(selector);
  function urlFor(form) {
    const url = new URL(form.action || location.href);
    url.search = new URLSearchParams(new FormData(form)).toString();
    url.searchParams.delete("pagina");
    if (url.searchParams.get("periodo") !== "custom") {
      url.searchParams.delete("inizio");
      url.searchParams.delete("fine");
    }
    const options = [...form.querySelectorAll('[name="sottocategoria"][type="checkbox"]')];
    if (form.dataset.categoriesChanged || (options.length && options.every((el) => el.checked)))
      url.searchParams.delete("sottocategoria");
    return url;
  }
  async function navigate(input, historyMode = "push") {
    clearTimeout(timer);
    const url = new URL(input, location.href);
    if (url.origin !== location.origin) return;
    pending?.abort();
    const controller = (pending = new AbortController());
    document.body.classList.add("is-loading");
    qs("#update-status").textContent = "Aggiornamento in corso…";
    try {
      const response = await fetch(url, {signal: controller.signal, headers: {"X-Requested-With": "XMLHttpRequest"}});
      if (!response.ok) throw new Error("Caricamento non riuscito");
      const doc = new DOMParser().parseFromString(await response.text(), "text/html");
      if (controller.signal.aborted) return;
      const content = doc.querySelector(".page-content");
      if (!content) return location.assign(url);
      // Capture the current UI, including panels closed while a request was pending.
      const x = scrollX, y = scrollY;
      const details = [...document.querySelectorAll("[data-persist]")].map(d => [d.dataset.persist, d.open, d.querySelector('.multi-options')?.scrollTop || 0]);
      const focus = document.activeElement;
      const focusName = focus?.name, focusValue = focus?.value;
      const selection = focus?.selectionStart;
      document.querySelectorAll("[data-chart]").forEach(el => window.Plotly?.purge(el));
      qs(".page-content").replaceWith(content);
      document.title = doc.title;
      if (historyMode === "push") history.pushState({}, "", url);
      details.forEach(([key, open, top]) => {
        const panel = qs(`[data-persist="${key}"]`);
        if (panel) {
          panel.open = open;
          const options = panel.querySelector('.multi-options');
          if (options) options.scrollTop = top;
        }
      });
      window.Wallet.init(content);
      if (focusName) {
        const inputs = [...content.querySelectorAll(`[name="${CSS.escape(focusName)}"]`)];
        const input = inputs.find(el => el.type !== 'hidden' && (el.type !== 'checkbox' || el.value === focusValue));
        if (input && input.getClientRects().length) {
          input.focus({preventScroll: true});
          if (selection != null && ['text', 'search'].includes(input.type)) input.setSelectionRange(selection, selection);
        }
      }
      requestAnimationFrame(() => scrollTo({left: x, top: y, behavior: "instant"}));
      qs("#update-status").textContent = "Contenuti aggiornati.";
    } catch (error) {
      if (error.name !== "AbortError") location.assign(url);
    } finally {
      if (pending === controller) document.body.classList.remove("is-loading");
    }
  }
  function validDates(form) {
    const fields = [...form.querySelectorAll('[data-date]')];
    fields.forEach(field => field.setCustomValidity(''));
    if (form.querySelector('[data-period-field]')?.value !== 'custom') return true;
    const dates = fields.map(field => {
      if (!field.value.trim()) return null;
      const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(field.value.trim());
      if (match) {
        const [, day, month, year] = match.map(Number);
        const value = new Date(year, month - 1, day);
        if (year >= 1000 && value.getFullYear() === year && value.getMonth() === month - 1 && value.getDate() === day) return value;
      }
      field.setCustomValidity('Inserisci una data valida nel formato gg/mm/aaaa.');
      return null;
    });
    if (dates[0] && dates[1] && dates[0] > dates[1])
      fields[1].setCustomValidity('La data finale deve essere uguale o successiva a quella iniziale.');
    return fields.every(field => field.validity.valid);
  }
  function apply(form) {
    clearTimeout(timer);
    if (form.isConnected && validDates(form) && form.reportValidity()) navigate(urlFor(form));
  }
  function schedule(form, delay = 180) {
    clearTimeout(timer);
    pending?.abort();
    timer = setTimeout(() => apply(form), delay);
  }
  function period(value) {
    const form = qs('#page-filters');
    if (!form) return;
    form.querySelector('[data-period-field]').value = value;
    apply(form);
  }
  document.addEventListener('submit', event => {
    if (!event.target.matches('[data-filter-form]')) return;
    event.preventDefault();
    apply(event.target);
  });
  document.addEventListener('click', event => {
    document.querySelectorAll('[data-filter-form] details[open]').forEach(panel => {
      if (!panel.contains(event.target)) panel.open = false;
    });
    const range = event.target.closest('[data-global-period], [data-period]');
    if (range) {event.preventDefault(); period(range.dataset.globalPeriod || range.dataset.period);}
    const link = event.target.closest('a[data-filter-link]');
    if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
      event.preventDefault(); navigate(link.href);
    }
    const select = event.target.closest('[data-select]');
    if (select) {
      const group = select.closest('.multi-select');
      const form = select.closest('form');
      if (group.querySelector('[name="categoria"]')) form.dataset.categoriesChanged = '1';
      group.querySelectorAll('input[type="checkbox"]').forEach(input => input.checked = select.dataset.select === 'all');
      apply(form);
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('[data-date], [data-search]')) {
      const form = event.target.closest('[data-filter-form]');
      if (form) {
        event.preventDefault();
        if (event.target.matches('[data-date]')) form.querySelector('[data-period-field]').value = 'custom';
        apply(form);
      }
    }
    if (event.key === 'Escape') document.querySelectorAll('[data-filter-form] details[open]').forEach(panel => panel.open = false);
  });
  document.addEventListener('change', event => {
    const target = event.target;
    if (target.matches('[data-month-picker]') && target.value) return period(target.value);
    if (target.matches('[data-sort-control], [data-page-size]')) {
      const url = new URL(location.href);
      url.searchParams.set(target.matches('[data-sort-control]') ? 'sort' : 'per_pagina', target.value);
      if (target.matches('[data-sort-control]')) url.searchParams.set('vista', 'tabella');
      url.searchParams.delete('pagina');
      return navigate(url);
    }
    const form = target.closest('[data-filter-form]');
    if (!form) return;
    if (target.matches('[data-date]')) {
      form.querySelector('[data-period-field]').value = 'custom';
      if (!validDates(form)) return;
    }
    if (target.name === 'categoria') form.dataset.categoriesChanged = '1';
    schedule(form);
  });
  document.addEventListener('input', event => {
    const target = event.target, form = target.closest('[data-filter-form]');
    if (!form) return;
    if (target.matches('[data-search]')) schedule(form, 350);
    if (target.matches('[data-date]')) {
      form.querySelector('[data-period-field]').value = 'custom';
      clearTimeout(timer);
      pending?.abort();
      if (validDates(form)) schedule(form, 500);
    }
  });
  window.addEventListener('popstate', () => navigate(location.href, 'none'));
  return {navigate};
})();
