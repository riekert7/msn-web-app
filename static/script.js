document.addEventListener('DOMContentLoaded', function() {
    const moduleSelect = document.getElementById('module');
    const emailInput = document.getElementById('email');
    const phoneInput = document.getElementById('phone');
    const fileInput = document.getElementById('proofOfPayment');
    const fileUploadArea = document.getElementById('fileUploadArea');
    const filePreview = document.getElementById('filePreview');
    const disclaimerCheckbox = document.getElementById('disclaimerAgree');
    const submitBtn = document.getElementById('submitBtn');
    const form = document.getElementById('studyNotesForm');

    const moduleSections = {
        'EKN110': document.getElementById('ekn110Section'),
        'EKN120': document.getElementById('ekn120Section'),
        'EKN214': document.getElementById('ekn214Section')
    };

    const costDisplays = {
        'EKN110': document.getElementById('ekn110Cost'),
        'EKN120': document.getElementById('ekn120Cost'),
        'EKN214': document.getElementById('ekn214Cost')
    };

    const totalCostDisplay = document.getElementById('totalCost');

    let selectedModule = '';
    let totalCost = 0;
    let uploadedFile = null;

    initializeForm();

    function initializeForm() {
        setupBankingDetailsCopy();
        moduleSelect.addEventListener('change', handleModuleChange);
        emailInput.addEventListener('blur', validateEmail);
        emailInput.addEventListener('input', clearEmailError);
        phoneInput.addEventListener('input', formatPhone);
        setupFileUpload();
        setupCostCalculation();
        disclaimerCheckbox.addEventListener('change', updateSubmitButton);
        form.addEventListener('submit', handleFormSubmission);
        updateSubmitButton();
    }

    function setupBankingDetailsCopy() {
        document.querySelectorAll('.bank-copy-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const target = document.getElementById(btn.dataset.copyTarget);
                if (!target) return;
                try {
                    await navigator.clipboard.writeText(target.textContent.trim());
                    const original = btn.textContent;
                    btn.textContent = 'Copied!';
                    setTimeout(() => { btn.textContent = original; }, 1500);
                } catch {
                    btn.textContent = 'Failed';
                }
            });
        });
    }

    function handleModuleChange() {
        const selectedValue = moduleSelect.value;

        Object.values(moduleSections).forEach(section => {
            if (section) {
                section.style.display = 'none';
                section.classList.remove('active');
            }
        });

        clearAllCheckboxes();

        if (selectedValue && moduleSections[selectedValue]) {
            moduleSections[selectedValue].style.display = 'block';
            moduleSections[selectedValue].classList.add('active');
            selectedModule = selectedValue;
        } else {
            selectedModule = '';
        }

        updateAllCosts();
        updateSubmitButton();
    }

    function clearAllCheckboxes() {
        document.querySelectorAll('input[name="chapters"]').forEach(cb => { cb.checked = false; });
    }

    function setupCostCalculation() {
        document.querySelectorAll('input[name="chapters"]').forEach(cb => {
            cb.addEventListener('change', updateAllCosts);
        });
    }

    function updateAllCosts() {
        let grandTotal = 0;

        Object.keys(moduleSections).forEach(module => {
            const moduleTotal = calculateModuleCost(module);
            if (costDisplays[module]) {
                costDisplays[module].textContent = `R ${formatCost(moduleTotal)}`;
            }
            grandTotal += moduleTotal;
        });

        totalCost = grandTotal;
        totalCostDisplay.textContent = `R ${formatCost(totalCost)}`;
        updateSubmitButton();
    }

    function formatCost(amount) {
        return amount % 1 === 0 ? amount : amount.toFixed(2);
    }

    function calculateModuleCost(module) {
        let total = 0;
        document.querySelectorAll(`input[name="chapters"][value^="${module}"]`).forEach(cb => {
            if (cb.checked) total += parseFloat(cb.dataset.cost) || 0;
        });
        return total;
    }

    function validateEmail() {
        const email = emailInput.value.trim();
        const errorDiv = document.getElementById('emailError');

        if (email && email.toLowerCase().includes('@icloud.com')) {
            showError(errorDiv, 'iCloud emails are not accepted. Please use a different email provider.');
            emailInput.classList.add('error');
            return false;
        } else if (email && !isValidEmail(email)) {
            showError(errorDiv, 'Please enter a valid email address.');
            emailInput.classList.add('error');
            return false;
        } else {
            hideError(errorDiv);
            emailInput.classList.remove('error');
            if (email) emailInput.classList.add('success');
            return true;
        }
    }

    function clearEmailError() {
        hideError(document.getElementById('emailError'));
        emailInput.classList.remove('error');
    }

    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function formatPhone() {
        let phone = phoneInput.value.replace(/\D/g, '');

        if (phone.length > 0 && !phone.startsWith('0')) {
            phone = '0' + phone;
        }

        if (phone.length > 3 && phone.length <= 6) {
            phone = phone.slice(0, 3) + ' ' + phone.slice(3);
        } else if (phone.length > 6) {
            phone = phone.slice(0, 3) + ' ' + phone.slice(3, 6) + ' ' + phone.slice(6, 10);
        }

        phoneInput.value = phone;
    }

    function setupFileUpload() {
        fileUploadArea.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileSelection);
        fileUploadArea.addEventListener('dragover', handleDragOver);
        fileUploadArea.addEventListener('dragleave', handleDragLeave);
        fileUploadArea.addEventListener('drop', handleFileDrop);
    }

    function handleFileSelection(event) {
        const file = event.target.files[0];
        if (file) validateAndDisplayFile(file);
    }

    function handleDragOver(event) {
        event.preventDefault();
        fileUploadArea.classList.add('dragover');
    }

    function handleDragLeave() {
        fileUploadArea.classList.remove('dragover');
    }

    function handleFileDrop(event) {
        event.preventDefault();
        fileUploadArea.classList.remove('dragover');
        const files = event.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            validateAndDisplayFile(files[0]);
        }
    }

    function validateAndDisplayFile(file) {
        const errorDiv = document.getElementById('fileError');
        const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];

        if (!allowedTypes.includes(file.type)) {
            showError(errorDiv, 'Invalid file type. Please upload a PDF, JPG, or PNG file.');
            clearFileInput();
            return;
        }

        const maxSize = 5 * 1024 * 1024; // 5MB
        if (file.size > maxSize) {
            showError(errorDiv, 'File size too large. Please upload a file smaller than 5MB.');
            clearFileInput();
            return;
        }

        hideError(errorDiv);
        uploadedFile = file;
        displayFilePreview(file);
        updateSubmitButton();
    }

    function displayFilePreview(file) {
        const fileSize = (file.size / 1024 / 1024).toFixed(2);
        const fileIcon = getFileIcon(file.type);

        filePreview.innerHTML = `
            <div class="file-info">
                <span class="file-icon">${fileIcon}</span>
                <div class="file-details">
                    <div class="file-name">${file.name}</div>
                    <div class="file-size">${fileSize} MB</div>
                </div>
                <button type="button" onclick="clearFileInput()" style="background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">Remove</button>
            </div>
        `;
        filePreview.classList.add('show');
    }

    function getFileIcon(fileType) {
        if (fileType === 'application/pdf') return '📄';
        if (fileType.startsWith('image/')) return '🖼️';
        return '📁';
    }

    window.clearFileInput = function() {
        fileInput.value = '';
        uploadedFile = null;
        filePreview.classList.remove('show');
        filePreview.innerHTML = '';
        hideError(document.getElementById('fileError'));
        updateSubmitButton();
    };

    function updateSubmitButton() {
        const isValid =
            selectedModule !== '' &&
            getSelectedChapters().length > 0 &&
            emailInput.value && validateEmail() &&
            phoneInput.value.trim() !== '' &&
            document.getElementById('firstName').value.trim() !== '' &&
            document.getElementById('lastName').value.trim() !== '' &&
            uploadedFile !== null &&
            disclaimerCheckbox.checked &&
            totalCost > 0;

        submitBtn.disabled = !isValid;
    }

    function getSelectedChapters() {
        return Array.from(document.querySelectorAll('input[name="chapters"]:checked')).map(cb => cb.value);
    }

    let isSubmitting = false;

    function handleFormSubmission(event) {
        event.preventDefault();

        if (isSubmitting) return;
        if (!validateForm()) return;

        isSubmitting = true;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Processing...';
        document.getElementById('loadingSpinner').style.display = 'block';

        const formData = new FormData();
        formData.append('firstName', document.getElementById('firstName').value.trim());
        formData.append('lastName', document.getElementById('lastName').value.trim());
        formData.append('email', emailInput.value.trim());
        formData.append('phone', phoneInput.value.trim());
        formData.append('module', selectedModule);
        formData.append('chapters', JSON.stringify(getSelectedChapters()));
        formData.append('totalCost', totalCost);
        formData.append('proofOfPayment', uploadedFile);
        formData.append('timestamp', new Date().toISOString());

        submitFormData(formData);
    }

    async function submitFormData(formData) {
        try {
            const response = await fetch('/submit', { method: 'POST', body: formData });

            if (response.ok) {
                showSuccessMessage();
                // isSubmitting stays true — form is replaced on success
            } else {
                throw new Error('Submission failed');
            }
        } catch (error) {
            console.error('Submission error:', error);
            showErrorMessage();
            isSubmitting = false;
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Request';
            document.getElementById('loadingSpinner').style.display = 'none';
        }
    }

    function validateForm() {
        let isValid = true;

        ['firstName', 'lastName', 'email', 'phone'].forEach(id => {
            const el = document.getElementById(id);
            if (!el.value.trim()) {
                el.classList.add('error');
                isValid = false;
            } else {
                el.classList.remove('error');
            }
        });

        if (!validateEmail()) isValid = false;

        if (!selectedModule) {
            moduleSelect.classList.add('error');
            isValid = false;
        }

        if (getSelectedChapters().length === 0) {
            alert('Please select at least one chapter.');
            isValid = false;
        }

        if (!uploadedFile) {
            showError(document.getElementById('fileError'), 'Proof of payment is required.');
            isValid = false;
        }

        if (!disclaimerCheckbox.checked) {
            alert('Please read and agree to the disclaimer.');
            isValid = false;
        }

        return isValid;
    }

    function showSuccessMessage() {
        form.innerHTML = `
            <div style="text-align: center; padding: 40px; background: #d4edda; border-radius: 12px; margin: 20px 0;">
                <h2 style="color: #155724; margin-bottom: 15px;">✅ Request Submitted Successfully!</h2>
                <p style="color: #155724; font-size: 1.1rem;">
                    Thank you for your request! We've received your proof of payment and will process your order shortly.
                    You'll receive access to your study materials via Google Drive once approved.
                </p>
                <p style="color: #155724; margin-top: 15px;">
                    <strong>Total Cost:</strong> R ${formatCost(totalCost)}<br>
                    <strong>Module:</strong> ${selectedModule}<br>
                    <strong>Chapters:</strong> ${getSelectedChapters().length} selected
                </p>
            </div>
        `;
    }

    function showErrorMessage() {
        alert('There was an error submitting your request. Please try again or contact support.');
    }

    function showError(element, message) {
        element.textContent = message;
        element.classList.add('show');
    }

    function hideError(element) {
        element.classList.remove('show');
        element.textContent = '';
    }

    ['firstName', 'lastName', 'email', 'phone'].forEach(fieldId => {
        const field = document.getElementById(fieldId);
        field.addEventListener('input', updateSubmitButton);
        field.addEventListener('blur', updateSubmitButton);
    });
});
