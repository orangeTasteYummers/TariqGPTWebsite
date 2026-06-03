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