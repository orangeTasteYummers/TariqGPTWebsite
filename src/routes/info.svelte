<script lang=ts>
    import tariqPfp from "../assets/tariqgpt-logo.svg";

    let funFacts = [
        `<span class="fun-fact">Tariq has given himself several nicknames during 0.1-0.3, such as Tariquartet, Tariquantum, and more!</span>`,
        `<span class="fun-fact">Tariq has only been trained on a single machine!</span>`,
        `<span class="fun-fact">Tariq was started by only <i>2 people!</i></span>`,
        `<span class="fun-fact">Tariq is less than 10M parameters!</span>`,
        
    ];
    function getNewFact() {
        var newFact = Math.floor(Math.random()*funFacts.length)
        while (funFacts[newFact] == randomFact) {
            newFact = Math.floor(Math.random()*funFacts.length)
        }
        return newFact;
    }
    var randomFact = funFacts[getNewFact()];
</script>

<div class="info-page container"> 
    <h1 style="display:inline;">About Tariq &nbsp;</h1> 
    <p>This page will include much information on tariq, describing his early days, such as his training and funny events (images are tough to find as of now and will show up later!)</p>

    <h2>Tariq's Creation</h2>

    <h2>Model Info</h2>
    <h3>Tariq Prime</h3>
    <p>Tariq Prime, or Tariq0.1 was the very first released iteration of tariq, he had not a lot going for himself but sure loved the war of 1812</p>

    <h3 style="color: maroon;">Tariq 0.4 or "Red Tariq"</h3>
    <p>At this point Tariq has scraped wikipedia, and came accross not very positive information (at least we think so).</p>
    <p>Red Tariq was very <i>very</i> unprofessional compared to the other Tariqs, and claimed to be a not so great person (to be clear, he was only scraping through wikipedia, no other version is as hateful as him and we had no intetion of this happening), but in particular <b>HATES</b> a person named Johnrei, seriously, just type "johnrei" or something about an annoying person and he will never end rambling about how terrible the guy is.</p>
    <small>I almost feel bad for 0.4 sometimes.</small>

    <h3>Tariq 0.6 or "Fat tariq"</h3>
    <p>Tariq 0.6 by this point has had access to discord for a long time, he is the longest running version of Tariq, the second being 0.5.5. He linked us to an... odd twitter page, which I will not share.</p>
    <p>The reason 0.6 has been nicknamed by me fat tariq is because he is an issue as of now. He tripled and size and broke the optimizer for all of his checkpoints, requiring me or @poopypants (github) to have to fix it just him. Such greed.</p>

    <h3 style="color: #FEA6B1;">Tsundere Tariq</h3>
    
    <p >Tsun Tariq (Tsundere Tariq) is our very first joke model, though a month late of april fools, he was created, and we plan to keep updating him.</p>
    <p>Tsun Tariq was trained due to a recent meme of AI's acting like <a href="https://en.wikipedia.org/wiki/Tsundere">Tsunderes.</a> </p>
    <h2 style="position: relative">Fun Facts <button style="display: inline; position:absolute; margin-inline: 5px;" on:click={() => randomFact = funFacts[getNewFact()]}><i class="ti ti-refresh"></i></button></h2>
    <span class=fun-fact>Fun Fact: {@html randomFact}</span>
<button style="margin-inline: auto; margin-block: 12px" on:click={() => location.href = '#/'}>Back</button>
</div>

<style>

:global(html, body) {
    margin: 0;
    padding: 0;
    overflow-y: auto !important;
}
</style>


