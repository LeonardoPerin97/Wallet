window.WalletForms = (() => {
  function init(root = document) {
    const form = root.querySelector("[data-transaction-form]"),
      data = root.querySelector("#subcategory-data");
    if (form && data) {
      const subs = JSON.parse(data.textContent);
      const categories = JSON.parse(root.querySelector('#category-data').textContent);
      const category = form.querySelector('[name="category"]');
      const select = form.querySelector('[name="subcategory"]');
      const kindField = form.querySelector('[data-expense-kind]');
      const radios = [...kindField.querySelectorAll('input')];
      const flexible = ['Uscita necessaria', 'Uscita extra'];
      function paintChoices(input, rows) {
        const picker = input.closest('[data-choice-picker]');
        picker.querySelector('.choice-grid')?.remove();
        picker.querySelector('.choice-empty')?.remove();
        input.classList.add('choice-native');
        input.tabIndex = -1;
        input.setAttribute('aria-hidden', 'true');
        const grid = document.createElement('div');
        grid.className = 'choice-grid';
        grid.setAttribute('role', 'radiogroup');
        grid.setAttribute('aria-labelledby', picker.dataset.choiceLabel);
        grid.setAttribute('aria-required', 'true');
        rows.forEach((row, index) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'choice-card';
          button.dataset.value = row.id;
          button.style.setProperty('--color', row.color);
          button.setAttribute('role', 'radio');
          button.setAttribute('aria-checked', String(input.value === String(row.id)));
          button.tabIndex = input.value === String(row.id) || (!input.value && !index) ? 0 : -1;
          const swatch = document.createElement('i');
          swatch.className = 'choice-swatch';
          swatch.setAttribute('aria-hidden', 'true');
          const label = document.createElement('span');
          label.textContent = row.name;
          button.append(swatch, label);
          button.addEventListener('click', () => {
            input.value = String(row.id);
            input.dispatchEvent(new Event('change', {bubbles: true}));
          });
          grid.append(button);
        });
        grid.addEventListener('keydown', event => {
          const keys = ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp', 'Home', 'End'];
          if (!keys.includes(event.key)) return;
          const buttons = [...grid.querySelectorAll('button')];
          const index = buttons.indexOf(document.activeElement);
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
            (index + (['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 1) + buttons.length) % buttons.length;
          event.preventDefault();
          buttons[next]?.focus();
          buttons[next]?.click();
        });
        picker.append(grid);
        if (!rows.length) {
          const empty = document.createElement('small');
          empty.className = 'choice-empty';
          empty.textContent = 'Scegli prima una categoria.';
          picker.append(empty);
        }
        let error = picker.querySelector('.choice-error');
        if (!error) {
          error = document.createElement('small');
          error.className = 'choice-error';
          error.setAttribute('role', 'alert');
          error.textContent = 'Seleziona una voce.';
          error.hidden = true;
          picker.append(error);
          input.addEventListener('invalid', event => {
            event.preventDefault();
            error.hidden = false;
            picker.querySelector('button')?.focus();
          });
          input.addEventListener('change', () => {error.hidden = !!input.value;});
        }
      }
      function markChoice(input) {
        input.closest('[data-choice-picker]').querySelectorAll('.choice-card').forEach(button => {
          const selected = button.dataset.value === input.value;
          button.setAttribute('aria-checked', String(selected));
          button.tabIndex = selected ? 0 : -1;
        });
      }
      function syncKind(reset = false) {
        const selected = subs.find(row => String(row.id) === select.value);
        const editable = !!selected && flexible.includes(selected.kind);
        kindField.hidden = !editable;
        radios.forEach(radio => {
          radio.disabled = !editable;
          if (reset || !radios.some(item => item.checked)) radio.checked = editable && radio.value === selected.kind;
        });
        form.querySelector('[data-derived-kind]').textContent = selected && !editable ? selected.kind : '';
      }
      const refresh = (initial = false) => {
        const previous = select.value;
        const rows = subs.filter(row => String(row.category_id) === category.value);
        select.replaceChildren(new Option('Scegli una sottocategoria', ''));
        rows.forEach(row => select.add(new Option(row.name, String(row.id))));
        if (rows.some(row => String(row.id) === previous)) select.value = previous;
        else if (rows.length === 1) select.value = String(rows[0].id);
        markChoice(category);
        paintChoices(select, rows);
        syncKind(!initial);
      };
      category.addEventListener('change', () => refresh());
      select.addEventListener('change', () => {markChoice(select); syncKind(true);});
      paintChoices(category, categories);
      refresh(true);
    }
    const transfer = root.querySelector("[data-transfer-form]");
    if (transfer) {
      const preview = transfer.querySelector("[data-transfer-preview]"),
        source = transfer.querySelector('[name="source"]'),
        dest = transfer.querySelector('[name="destination"]'),
        amount = transfer.querySelector('[name="amount"]');
      const update = () => {
        const same = source.value && source.value === dest.value;
        dest.setCustomValidity(same ? "Scegli due conti diversi." : "");
        if (same)
          preview.textContent =
            "Il conto di origine e quello di destinazione devono essere diversi.";
        else if (source.value && dest.value && amount.value)
          preview.textContent = `${amount.value} € da ${source.selectedOptions[0].text} a ${dest.selectedOptions[0].text}. Il saldo consolidato resta invariato.`;
        else
          preview.textContent =
            "L’importo viene sottratto dal conto di origine e aggiunto al conto di destinazione. Il saldo totale resta invariato.";
      };
      transfer.addEventListener("input", update);
      update();
    }
  }
  document.addEventListener("submit", (e) => {
    const message = e.target.dataset.confirm;
    if (message && !confirm(message)) e.preventDefault();
  });
  return { init };
})();
