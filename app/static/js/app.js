document.addEventListener("DOMContentLoaded", () => {
  const textarea = document.getElementById("todo-content");
  if (!textarea) return;
  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      textarea.form?.requestSubmit();
    }
  });
});
