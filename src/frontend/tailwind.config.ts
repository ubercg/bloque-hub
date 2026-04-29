import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'primary': '#3B82F6', // Bloque Hub primary blue
        'secondary': '#6B7280', // Gray for secondary actions
        'cta': '#10B981', // Green for call to action
        'background': '#F9FAFB', // Light gray background
        'text-default': '#1F2937', // Dark gray for main text
        'text-light': '#6B7280', // Lighter gray for secondary text
        'slot-uso': '#93C5FD', // Light blue for USO slots
        'slot-montaje': '#FDBA74', // Orange for MONTAJE slots
        'slot-desmontaje': '#FCA5A5', // Red for DESMONTAJE slots
        'slot-overlap-error': '#EF4444', // Red for overlap errors
        'border-default': '#E5E7EB', // Default border color
      },
      fontFamily: {
        display: ['"Inter var"', 'sans-serif'], // Example: Inter for display
        body: ['"Roboto Flex"', 'sans-serif'], // Example: Roboto Flex for body
      },
      boxShadow: {
        'soft': '0 4px 6px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.02)',
        'medium': '0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05)',
      },
      transitionProperty: {
        'colors': 'background-color, border-color, color, fill, stroke',
      },
      transitionDuration: {
        '150': '150ms',
        '300': '300ms',
      },
    },
  },
  plugins: [],
};
export default config;