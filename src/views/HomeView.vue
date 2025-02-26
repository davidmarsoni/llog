<template>
  <div class="container">
    <div class="content">
      <img alt="Vue logo" src="../assets/logo.png" class="logo">
      <h1 class="title">Welcome to Your App</h1>
      <div class="card">
        <UserList />
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import UserList from '@/components/UserList.vue';

export default defineComponent({
  name: 'HomeView',
  components: {
    UserList
  }
});
</script>

<style>
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 16px;
}

.content {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo {
  width: 96px;
  height: auto;
  margin-bottom: 32px;
}

.title {
  font-size: 2rem;
  font-weight: bold;
  margin-bottom: 24px;
  color: #1a202c; /* dark:text-gray-100 equivalent */
}

.card {
  width: 100%;
  max-width: 1024px;
  background-color: #ffffff; /* bg-white equivalent */
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  padding: 24px;
}

.album {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px;
  border-radius: 16px;
}

.cover {
  width: 48px;
  height: 48px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.details {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.info {
  display: flex;
  align-items: center;
}
</style>