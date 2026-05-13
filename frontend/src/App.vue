<script setup>
import ChatPanel from './components/ChatPanel.vue'
import CommandPanel from './components/CommandPanel.vue'
import ProgressPanel from './components/ProgressPanel.vue'
import ProjectSidebar from './components/ProjectSidebar.vue'
import ReportPanel from './components/ReportPanel.vue'
import SourceBrowser from './components/SourceBrowser.vue'
import ViewSwitcher from './components/ViewSwitcher.vue'
import { useProjectHelper } from './composables/useProjectHelper'

const workspace = useProjectHelper()
</script>

<template>
  <main class="shell">
    <CommandPanel
      v-model="workspace.repoUrl.value"
      :error="workspace.error.value"
      :loading="workspace.loading.value"
      :status-label="workspace.statusLabel.value"
      @submit="workspace.createAndAnalyze"
    />

    <section class="workspace">
      <ProjectSidebar
        :active-project-id="workspace.activeProject.value?.id"
        :busy-project-id="workspace.busyProjectId.value"
        :projects="workspace.projects.value"
        @delete="workspace.deleteProject"
        @load="workspace.loadProject"
        @toggle-pin="workspace.togglePinned"
      />

      <section class="main-grid">
        <ProgressPanel
          :is-cached-run="workspace.isCachedRun.value"
          :latest-progress="workspace.latestProgress.value"
          :pipeline-steps="workspace.pipelineSteps"
          :progress="workspace.progress.value"
          :progress-log="workspace.progressLog.value"
          :progress-percent="workspace.progressPercent.value"
          :status-label="workspace.statusLabel.value"
          :step-state="workspace.stepState"
        />

        <ViewSwitcher
          :active-view="workspace.activeView.value"
          :tabs="workspace.workspaceTabs.value"
          @select="workspace.selectView"
        />

        <SourceBrowser
          v-show="workspace.activeView.value === 'source'"
          :annotation-error="workspace.sourceAnnotationError.value"
          :annotation-loading="workspace.sourceAnnotationLoading.value"
          :annotation-saving="workspace.sourceAnnotationSaving.value"
          :annotations="workspace.sourceAnnotations.value"
          :error="workspace.sourceError.value"
          :file="workspace.sourceFile.value"
          :file-loading="workspace.sourceFileLoading.value"
          :is-ready="workspace.isReady.value"
          :loading="workspace.sourceLoading.value"
          :tree="workspace.sourceTree.value"
          @create-annotation="workspace.createSourceAnnotation"
          @delete-annotation="workspace.deleteSourceAnnotation"
          @load-file="workspace.loadSourceFile"
          @refresh="workspace.fetchSourceTree"
          @update-annotation="workspace.updateSourceAnnotation"
        />

        <ReportPanel
          v-show="workspace.activeView.value === 'report'"
          :project="workspace.activeProject.value"
        />

        <ChatPanel
          v-show="workspace.activeView.value === 'chat'"
          v-model="workspace.question.value"
          :asking="workspace.asking.value"
          :is-ready="workspace.isReady.value"
          :messages="workspace.chatMessages.value"
          :source-tree="workspace.sourceTree.value"
          :referenced-files="workspace.referencedFiles.value"
          @ask="workspace.askQuestion"
          @stop="workspace.stopQuestion"
          @update:referenced-files="(files) => workspace.referencedFiles.value = files"
        />
      </section>
    </section>
  </main>
</template>
