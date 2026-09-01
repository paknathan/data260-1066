const isValidSubmission = (description, Acceptance) => {
    if (description.length <= 25) return "Description is too short";
    const isBoxChecked = document.getElementById(Acceptance).checked;
    if (isBoxChecked == false) return "Box is not checked"
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

document.querySelector("form").addEventListener("submit", (event) => {
    const description = document.getElementById("description").value;
    const result = isValidSubmission(description, "Acceptance");

    if (result !== true) {
        event.preventDefault();
        alert(result);
        return;
    }

    const formElement = document.querySelector("form");
    const formData = new FormData(formElement);
    const jsonString = JSON.stringify(Object.fromEntries(formData));
    const jsonObject = JSON.parse(jsonString);
    const {incident_id, email} = jsonObject;
    const updatedJsonObject = {...jsonObject, submissionDate: new Date()};


    console.log(jsonString);
    console.log(incident_id);
    console.log(email);
    console.log(updatedJsonObject);
    console.log(counter());

    event.preventDefault();
});
