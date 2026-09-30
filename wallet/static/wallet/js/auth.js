document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  const input = document.getElementById(button.getAttribute("aria-controls"));
  if (!input) return;
  button.hidden = false;
  button.addEventListener("click", () => {
    const reveal = input.type === "password";
    input.type = reveal ? "text" : "password";
    button.setAttribute("aria-pressed", String(reveal));
    button.setAttribute(
      "aria-label",
      reveal ? "Nascondi password" : "Mostra password",
    );
    button
      .querySelector("use")
      .setAttribute("href", reveal ? "#i-eye-off" : "#i-eye");
  });
});
