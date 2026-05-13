import { createApp, h } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import { darkTheme, NConfigProvider, NDialogProvider } from 'naive-ui'
import 'highlight.js/styles/github-dark.css'
import {
  BookOpen,
  BookOpenCheck,
  Bot,
  Blocks,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleStop,
  Activity,
  DatabaseZap,
  Code2,
  Database,
  FileCode2,
  FileText,
  Filter,
  FolderTree,
  FolderGit2,
  FolderOpen,
  GitBranch,
  GitPullRequestArrow,
  Loader2,
  MessageSquarePlus,
  MessageSquareText,
  Pin,
  PinOff,
  Play,
  RadioTower,
  RefreshCw,
  Search,
  ScanSearch,
  Sparkles,
  TerminalSquare,
  Trash2,
  User,
  Zap,
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
app.component('BookOpenCheck', BookOpenCheck)
app.component('Bot', Bot)
app.component('Blocks', Blocks)
app.component('CheckCircle2', CheckCircle2)
app.component('ChevronDown', ChevronDown)
app.component('ChevronRight', ChevronRight)
app.component('CircleStop', CircleStop)
app.component('Activity', Activity)
app.component('DatabaseZap', DatabaseZap)
app.component('Code2', Code2)
app.component('Database', Database)
app.component('FileCode2', FileCode2)
app.component('FileText', FileText)
app.component('Filter', Filter)
app.component('FolderTree', FolderTree)
app.component('FolderGit2', FolderGit2)
app.component('FolderOpen', FolderOpen)
app.component('GitBranch', GitBranch)
app.component('GitPullRequestArrow', GitPullRequestArrow)
app.component('Loader2', Loader2)
app.component('MessageSquarePlus', MessageSquarePlus)
app.component('MessageSquareText', MessageSquareText)
app.component('Pin', Pin)
app.component('PinOff', PinOff)
app.component('Play', Play)
app.component('RadioTower', RadioTower)
app.component('RefreshCw', RefreshCw)
app.component('Search', Search)
app.component('ScanSearch', ScanSearch)
app.component('Sparkles', Sparkles)
app.component('TerminalSquare', TerminalSquare)
app.component('Trash2', Trash2)
app.component('User', User)
app.component('Zap', Zap)
app.mount('#app')
