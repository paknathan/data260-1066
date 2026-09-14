const isValidSubmission = (description, Acceptance) => {
    if (description.length <= 25) return "Description is too short (must be > 25 characters).";
    const isBoxChecked = document.getElementById(Acceptance).checked;
    if (isBoxChecked === false) return "You must accept the terms and conditions.";
    return true;
};

function createCounter() {
    let count = 0;
    return function() {
        count++;
        return count;
    };
}

const counter = createCounter();

document.getElementById("incidentForm").addEventListener("submit", (event) => {
    event.preventDefault();

    const submitButton = document.getElementById("submitButton");
    const status = document.getElementById("status");
    const errorMessage = document.getElementById("errorMessage");
    const loadingIndicator = document.getElementById("loadingIndicator");

    // Reset error container state
    errorMessage.textContent = "";
    errorMessage.classList.add("hidden");

    const description = document.getElementById("description").value;
    const result = isValidSubmission(description, "Acceptance");

    // 1. ERROR STATE IMPLEMENTATION
    if (result !== true) {
        errorMessage.textContent = result;
        errorMessage.classList.remove("hidden");
        return;
    }

    // 2. LOADING STATE IMPLEMENTATION
    submitButton.disabled = true;
    submitButton.textContent = "Submitting...";
    loadingIndicator.classList.add("hidden");
    loadingIndicator.classList.remove("hidden");

    // Simulate short network delay to display loading state
    setTimeout(() => {
        const formElement = document.querySelector("form");
        const formData = new FormData(formElement);
        const jsonString = JSON.stringify(Object.fromEntries(formData));
        const jsonObject = JSON.parse(jsonString);

        const { incident_id, email } = jsonObject;
        const updatedJsonObject = { ...jsonObject, submissionDate: new Date() };

        console.log("Logged JSON String:", jsonString);
        console.log("Incident ID:", incident_id);
        console.log("Email:", email);
        console.log("Updated Object:", updatedJsonObject);
        console.log("Submission Count:", counter());

        // 3. CLEAR EMPTY STATE & DISPLAY SUCCESS
        loadingIndicator.classList.add("hidden");
        submitButton.disabled = false;
        submitButton.textContent = "Submit";

        status.textContent = `Incident ${incident_id} successfully logged to console!`;
        status.classList.remove("hidden", "empty-state");
        status.classList.add("success-state");

        // Optional: Reset form fields after submission
        formElement.reset();
    }, 600);
});