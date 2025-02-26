import axios, { AxiosInstance } from 'axios';

/**
 * Axios instance for making HTTP requests to the API.
 * 
 * @const {AxiosInstance} api - The configured Axios instance
 */
const api: AxiosInstance = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 5000,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFTOKEN',
  withXSRFToken: true,
  headers: {
    'Content-Type': 'application/json'
  }
});

export default api;