/* Shared application shell. Feature modules own charts, filters and forms. */
window.Wallet = {
  init(root = document) {
    const sort = root.querySelector("[data-sort-control]");
    if (sort)
      sort.value = new URL(location.href).searchParams.get("sort") || "-date";
    window.WalletCharts?.init(root);
    window.WalletForms?.init(root);
    window.WalletBudget?.init(root);
  },
};
document.addEventListener("DOMContentLoaded", () => {
  Wallet.init();
  const dialog = document.querySelector("#new-movement-dialog");
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-new-movement]");
    if (button) {
      dialog.querySelectorAll("[data-new-link]").forEach((link) => {
        const url = new URL(link.href);
        url.searchParams.delete("conto");
        if (button.dataset.account)
          url.searchParams.set("conto", button.dataset.account);
        link.href = url;
      });
      dialog.showModal();
    }
    if (event.target.closest("[data-close-dialog]")) dialog.close();
    const flow = event.target.closest("[data-flow]");
    if (flow) WalletCharts.flow(flow.dataset.flow);
    if (event.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (
        event.clientX < r.left ||
        event.clientX > r.right ||
        event.clientY < r.top ||
        event.clientY > r.bottom
      )
        dialog.close();
    }
  });
});
