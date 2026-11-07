import {defineConfig,loadEnv} from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig(({mode})=>{const target=loadEnv(mode,'.','').API_TARGET||'http://127.0.0.1:8010';return {plugins:[tailwindcss()],server:{proxy:{'/api':target,'/health':target}},preview:{proxy:{'/api':target,'/health':target}}};});
