/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      keyframes: {
        emailPanelIn: {
          "0%": { opacity: "0.72", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "email-panel-in": "emailPanelIn 0.2s ease-out both",
      },
    },
  },
  plugins: [],
};
