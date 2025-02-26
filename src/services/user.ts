import api from './api';

/**
 * Fetches the list of users from the API.
 *
 * @returns {Promise<any>} The list of users
 */
export const getUserList = async (): Promise<any> => {
  try {
    const response = await api.get('/users');
    return response.data;
  } catch (error) {
    console.error('Error fetching user list:', error);
    throw error;
  }
};
