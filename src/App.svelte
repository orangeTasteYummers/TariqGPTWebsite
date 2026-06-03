<script lang=ts>
    //routing
    import Router from 'svelte-spa-router';
    import Home from './routes/Home.svelte';
    import Info from './routes/info.svelte';
    
    const routes = {
        '/': Home,
        '/info': Info,
    }
</script>

<Router {routes}/>

<style>

:global(html, body) {
    margin: 0;
    padding: 0;
    overflow-y: hidden;
}
</style>
