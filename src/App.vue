<template>
  <div id="app" >
    <HomeView />
  </div>
</template>
<script lang="ts">
import { Options, Vue } from 'vue-class-component';
import HomeView from './views/HomeView.vue';

@Options({
  components: {
    HomeView,
  },
})
export default class App extends Vue {
  isDarkMode = false;

  mounted() {
    // Check for saved theme preference or system preference
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
      this.isDarkMode = savedTheme === 'dark';
    } else {
      // Check system preference
      this.isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
  }
}
</script>

<style>
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  min-height: 100vh;
  transition: background-color 0.3s;
}

button.dark-mode {
  background-color: #374151;
  color: #f3f4f6;
  border-color: #4b5563;
}

button.light-mode {
  background-color: #f3f4f6;
  color: #1f2937;
  border-color: #d1d5db;
}

button.dark-mode:hover {
  background-color: #4b5563;
  color: #e5e7eb;
}

button.light-mode:hover {
  background-color: #e5e7eb;
  color: #1f2937;
}

button.dark-mode:focus {
  outline: 2px solid #6b7280;
}

button.light-mode:focus {
  outline: 2px solid #d1d5db;
}

button.dark-mode:active {
  background-color: #4b5563;
}

button.light-mode:active {
  background-color: #e5e7eb;
}
</style>