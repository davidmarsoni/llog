<template>
  <div class="user-container">
    <h2 class="title">User List</h2>
    <div v-if="loading" class="message">Loading users...</div>
    <div v-else-if="error" class="error-message">Failed to load users: {{ error }}</div>
    <ul v-else-if="users.length > 0" class="user-list">
      <li v-for="user in users" 
          :key="user.id"
          class="user-item">
        {{ user.username }} ({{ user.email }})
      </li>
    </ul>
    <div v-else class="message">No users found.</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import { getUserList } from '@/services/user';

// Define user interface
interface User {
  id: number;
  username: string;
  email: string;
}

export default defineComponent({
  name: 'UserList',
  setup() {
    const users = ref<User[]>([]);
    const loading = ref(true);
    const error = ref('');

    const fetchUsers = async () => {
      try {
        loading.value = true;
        error.value = '';
        users.value = await getUserList();
      } catch (err) {
        error.value = err instanceof Error ? err.message : 'Unknown error';
      } finally {
        loading.value = false;
      }
    };

    onMounted(fetchUsers);

    return {
      users,
      loading,
      error
    };
  }
});
</script>
