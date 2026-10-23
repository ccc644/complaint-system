/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#4F46E5',
        success: '#16A34A',
        danger: '#DC2626',
        warning: '#CA8A04',
        // 0820 修复：单值定义会覆盖 Tailwind 默认 orange 色阶，导致 bg-orange-600 等类静默失效
        // （未解决按钮白底白字）。改对象形式与默认色阶合并，DEFAULT 保持原值。
        orange: { DEFAULT: '#EA580C' },
        // 0820 修复：与 orange 同类问题——单值定义覆盖默认 violet 色阶，导致 bg-violet-600 等类失效
        // （邮件审核按钮白底白字）。改对象形式与默认色阶合并，DEFAULT 保持原值。
        violet: { DEFAULT: '#7C3AED' },
      },
      borderRadius: {
        base: '6px',
      },
    },
  },
  plugins: [],
}
