// 🔍 SEARCH SYSTEM (multi keyword smart search)
function searchApp() {
    let input = document.getElementById('search').value.toLowerCase().trim();
    let keywords = input.split(" ");
    let cards = document.getElementsByClassName('card');

    for (let i = 0; i < cards.length; i++) {

        let title = cards[i].getElementsByTagName("h2")[0].innerText.toLowerCase();
        let desc = cards[i].getElementsByTagName("p")[0].innerText.toLowerCase();

        let fullText = title + " " + desc;

        let match = true;

        for (let j = 0; j < keywords.length; j++) {
            if (!fullText.includes(keywords[j])) {
                match = false;
                break;
            }
        }

        cards[i].style.display = match ? "" : "none";
    }
}


// ⭐ RATING SYSTEM
let stars = document.querySelectorAll(".rating span");

stars.forEach(star => {
    star.addEventListener("click", () => {

        let value = star.getAttribute("data-value");

        // reset all
        let parent = star.parentElement;
        let allStars = parent.querySelectorAll("span");

        allStars.forEach(s => s.classList.remove("active"));

        // fill stars
        for (let i = 0; i < value; i++) {
            allStars[i].classList.add("active");
        }

        alert("You rated this " + value + " ⭐ stars");
    });
});
