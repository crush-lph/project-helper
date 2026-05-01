import { createApp, h } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import { darkTheme, NConfigProvider, NDialogProvider } from 'naive-ui'
import 'highlight.js/styles/github-dark.css'
import {
  BookOpen,
  Bot,
  CheckCircle2,
  Code2,
  Database,
  FolderGit2,
  Loader2,
  MessageSquareText,
  Pin,
  PinOff,
  Play,
  Search,
  Sparkles,
  TerminalSquare,
  Trash2,
} from 'lucide-vue-next'
import './styles.css'
import App from './App.vue'

const naiveThemeOverrides = {
  common: {
    primaryColor: '#22c55e',
    primaryColorHover: '#4ade80',
    primaryColorPressed: '#16a34a',
    primaryColorSuppl: '#86efac',
    borderRadius: '8px',
  },
  Dialog: {
    color: '#0f172a',
    titleTextColor: '#f8fafc',
    textColor: '#cbd5e1',
    borderRadius: '8px',
  },
}

marked.setOptions({
  gfm: true,
  breaks: true,
  highlight(code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext'
    return hljs.highlight(code, { language }).value
  },
})

const Root = {
  render() {
    return h(
      NConfigProvider,
      { theme: darkTheme, themeOverrides: naiveThemeOverrides },
      {
        default: () => h(NDialogProvider, null, { default: () => h(App) }),
      },
    )
  },
}

const app = createApp(Root)
app.config.globalProperties.$marked = marked
app.component('BookOpen', BookOpen)
app.component('Bot', Bot)
app.component('CheckCircle2', CheckCircle2)
app.component('Code2', Code2)
app.component('Database', Database)
app.component('FolderGit2', FolderGit2)
app.component('Loader2', Loader2)
app.component('MessageSquareText', MessageSquareText)
app.component('Pin', Pin)
app.component('PinOff', PinOff)
app.component('Play', Play)
app.component('Search', Search)
app.component('Sparkles', Sparkles)
app.component('TerminalSquare', TerminalSquare)
app.component('Trash2', Trash2)
app.mount('#app')
