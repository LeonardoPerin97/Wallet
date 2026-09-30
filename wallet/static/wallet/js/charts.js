/* Amounts arrive as decimal strings. Number conversion is only for chart geometry. */
window.WalletCharts = (() => {
  const base = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, Segoe UI, sans-serif", color: "#667895", size: 12 },
    margin: { l: 15, r: 14, t: 16, b: 35 },
    separators: ",.",
    hoverlabel: { bgcolor: "#112954", font: { color: "#fff" } },
    xaxis: { showgrid: false, automargin: true },
    yaxis: {
      gridcolor: "#edf1f8",
      zerolinecolor: "#d9e2f0",
      ticksuffix: " €",
      tickformat: ",.0f",
      automargin: true,
    },
    legend: { orientation: "h", y: -0.25, x: 0, font: { size: 11 } },
    barmode: "stack",
    bargap: 0.35,
  };
  const config = {
    responsive: true,
    displayModeBar: false,
    displaylogo: false,
  };
  let payload = {};
  function chartTooltip(el, name) {
    const wrap = el.closest(".donut-wrap, .chart-tooltip-wrap");
    if (!wrap || el.dataset.tooltipReady) return;
    el.dataset.tooltipReady = "1";
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip" + (name === "donut" ? " donut-tooltip" : name === "daily" ? " line-tooltip" : " bar-tooltip");
    tooltip.setAttribute("role", "tooltip");
    tooltip.hidden = true;
    const title = document.createElement("strong");
    const values = document.createElement("dl");
    const labels = name === "donut" ? ["Importo", "Percentuale", "Movimenti"] : name === "daily" ? ["Data", "Saldo"] : ["Mese", "Importo"];
    const fields = labels.map(label => {
      const term = document.createElement("dt");
      const value = document.createElement("dd");
      term.textContent = label;
      values.append(term, value);
      return value;
    });
    tooltip.append(title, values);
    wrap.append(tooltip);
    el.on("plotly_hover", event => {
      const point = event.points?.[0];
      if (!point) return;
      const index = point.pointNumber;
      const trace = el.data[point.curveNumber];
      const date = name === "daily" ? String(trace.x[index]).split("-").reverse().join("/") : trace.x?.[index];
      const row = name === "donut" ? trace.customdata[index] : [date, trace.customdata[index]];
      title.textContent = name === "donut" ? trace.labels[index] : trace.name;
      fields.forEach((field, i) => field.textContent = row[i]);
      tooltip.hidden = false;
      const box = wrap.getBoundingClientRect();
      const pointer = event.event;
      let left = (pointer?.clientX ?? box.x + box.width / 2) - box.x + 16;
      let top = (pointer?.clientY ?? box.y + box.height / 2) - box.y + 16;
      if (left + tooltip.offsetWidth > box.width - 8) left -= tooltip.offsetWidth + 32;
      if (top + tooltip.offsetHeight > box.height - 8) top -= tooltip.offsetHeight + 32;
      tooltip.style.left = `${Math.max(8, left)}px`;
      tooltip.style.top = `${Math.max(8, top)}px`;
    });
    const hide = () => {tooltip.hidden = true;};
    el.on("plotly_unhover", hide);
    el.on("plotly_restyle", hide);
    el.on("plotly_afterplot", hide);
    el.addEventListener("pointerleave", hide);
  }
  function render(el, traces, name) {
    const customTooltip = ["donut", "daily", "flows", "net", "spending"].includes(name);
    if (customTooltip && name !== "donut" && !el.parentElement.matches(".chart-tooltip-wrap")) {
      const wrap = document.createElement("div");
      wrap.className = "chart-tooltip-wrap";
      el.before(wrap);
      wrap.append(el);
    }
    const anchor = el.closest(".chart-tooltip-wrap") || el;
    const layout = structuredClone(base);
    layout.font.family = getComputedStyle(document.body).fontFamily;
    if (name === "donut") {
      layout.margin = { l: 10, r: 10, t: 10, b: 10 };
      layout.showlegend = false;
      layout.hoverlabel = {bgcolor: '#fff', bordercolor: '#dce4ef', align: 'left',
        font: {family: layout.font.family, color: '#162849', size: 13}};
    }
    if (name === "daily") {
      layout.showlegend = false;
      layout.hovermode = "x";
      layout.spikedistance = -1;
      Object.assign(layout.xaxis, {
        tickformat: "%d/%m",
        showspikes: true,
        spikemode: "across",
        spikesnap: "hovered data",
        spikedash: "dot",
        spikecolor: "#7b93bc",
        spikethickness: 1,
      });
    }
    if (name === "net") layout.showlegend = false;
    if (
      !traces?.length ||
      (name === "spending" && !traces.some((t) => t.y?.some((v) => Number(v))))
    ) {
      layout.annotations = [
        {
          text: "Nessun dato nel periodo selezionato",
          showarrow: false,
          xref: "paper",
          yref: "paper",
          x: 0.5,
          y: 0.5,
        },
      ];
    }
    const customLegend =
      name === "spending" || (name === "flows" && traces.length > 5);
    if (customLegend) layout.showlegend = false;
    if (anchor.nextElementSibling?.classList.contains("chart-series"))
      anchor.nextElementSibling.remove();
    const drawn = Plotly.react(el, traces || [], layout, config);
    if (customTooltip) drawn.then(() => chartTooltip(el, name));
    if (customLegend && traces.length) {
      const details = document.createElement("details");
      details.className = "chart-series";
      const summary = document.createElement("summary");
      summary.textContent = `Serie del grafico · ${traces.length} ▾`;
      details.append(summary);
      const options = document.createElement("div");
      options.className = "series-options";
      traces.forEach((trace, index) => {
        const label = document.createElement("label"),
          check = document.createElement("input"),
          dot = document.createElement("i");
        check.type = "checkbox";
        check.checked = true;
        dot.className = "dot";
        dot.style.setProperty(
          "--color",
          trace.marker?.color || trace.line?.color || "#1546ac",
        );
        check.addEventListener("change", () =>
          Plotly.restyle(el, { visible: check.checked ? true : "legendonly" }, [
            index,
          ]),
        );
        label.append(check, dot, document.createTextNode(trace.name));
        options.append(label);
      });
      const actions = document.createElement("div");
      actions.className = "selection-actions";
      [
        ["Mostra tutte", true],
        ["Nascondi tutte", false],
      ].forEach(([text, visible]) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = text;
        b.addEventListener("click", () => {
          options
            .querySelectorAll("input")
            .forEach((c) => (c.checked = visible));
          Plotly.restyle(el, { visible: visible ? true : "legendonly" });
        });
        actions.append(b);
      });
      details.append(actions, options);
      anchor.after(details);
    }
    return drawn;
  }
  function init(root = document) {
    const node = root.querySelector("#chart-data");
    if (!node || !window.Plotly) return;
    payload = JSON.parse(node.textContent);
    root.querySelectorAll("[data-chart]").forEach((el) => {
      const name = el.dataset.chart;
      render(el, name === "flows" ? payload.flows.totale : payload[name], name);
    });
  }
  function flow(mode) {
    const el = document.querySelector('[data-chart="flows"]');
    if (el) render(el, payload.flows[mode], "flows");
    document.querySelectorAll("[data-flow]").forEach((b) => {
      const active = b.dataset.flow === mode;
      b.classList.toggle("selected", active);
      b.setAttribute("aria-pressed", String(active));
    });
  }
  return { init, flow };
})();
