import { createApp } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
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
  Play,
  Search,
  Sparkles,
  TerminalSquare,
} from 'lucide-vue-next'
import './styles.css'
import App from './App.vue'

marked.setOptions({
  gfm: true,
  breaks: true,
  highlight(code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext'
    return hljs.highlight(code, { language }).value
  },
})

const app = createApp(App)
app.config.globalProperties.$marked = marked
app.component('BookOpen', BookOpen)
app.component('Bot', Bot)
app.component('CheckCircle2', CheckCircle2)
app.component('Code2', Code2)
app.component('Database', Database)
app.component('FolderGit2', FolderGit2)
app.component('Loader2', Loader2)
app.component('MessageSquareText', MessageSquareText)
app.component('Play', Play)
app.component('Search', Search)
app.component('Sparkles', Sparkles)
app.component('TerminalSquare', TerminalSquare)
app.mount('#app')
