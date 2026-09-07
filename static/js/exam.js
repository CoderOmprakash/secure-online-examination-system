let totalSeconds = duration * 60;

const timerElement =
    document.getElementById("time");

const examForm =
    document.getElementById("examForm");


function updateTimer() {

    const minutes =
        Math.floor(totalSeconds / 60);

    const seconds =
        totalSeconds % 60;


    timerElement.textContent =
        String(minutes).padStart(2, "0")
        +
        ":"
        +
        String(seconds).padStart(2, "0");


    if (totalSeconds <= 0) {

        clearInterval(timerInterval);

        alert(
            "Time is over. Exam will be submitted automatically."
        );

        examForm.submit();

        return;

    }


    totalSeconds--;

}


updateTimer();


const timerInterval =
    setInterval(
        updateTimer,
        1000
    );