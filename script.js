// 🔍 SMART SEARCH (image + text + tags)
function searchApp() {

    let input = document.getElementById('search').value.toLowerCase().trim();
    let keywords = input.split(" ");
    let cards = document.getElementsByClassName('card');

    for (let i = 0; i < cards.length; i++) {

        let title = cards[i].getElementsByTagName("h2")[0].innerText.toLowerCase();
        let desc = cards[i].getElementsByTagName("p")[0].innerText.toLowerCase();
        let img = cards[i].getElementsByTagName("img")[0].alt.toLowerCase();

        let fullText = title + " " + desc + " " + img;

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
document.addEventListener("DOMContentLoaded", () => {

    let stars = document.querySelectorAll(".rating span");

    stars.forEach(star => {
        star.addEventListener("click", () => {

            let value = star.getAttribute("data-value");

            let parent = star.parentElement;
            let all = parent.querySelectorAll("span");

            all.forEach(s => s.classList.remove("active"));

            for (let i = 0; i < value; i++) {
                all[i].classList.add("active");
            }

            alert("⭐ You rated " + value + " stars");
        });
    });

});
