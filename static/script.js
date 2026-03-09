// Copied from netlify-form/script.js with endpoint adjusted to /submit
document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const moduleSelect = document.getElementById('module');
    const emailInput = document.getElementById('email');
    const phoneInput = document.getElementById('phone');
    const fileInput = document.getElementById('proofOfPayment');
    const fileUploadArea = document.getElementById('fileUploadArea');
    const filePreview = document.getElementById('filePreview');
    const disclaimerCheckbox = document.getElementById('disclaimerAgree');
    const submitBtn = document.getElementById('submitBtn');
    const form = document.getElementById('studyNotesForm');
    
    // Module sections
    const moduleSections = {
        'EKN110': document.getElementById('ekn110Section'),
        'EKN120': document.getElementById('ekn120Section'),
        'EKN214': document.getElementById('ekn214Section')
    };
    
    // Cost displays
    const costDisplays = {
        'EKN110': document.getElementById('ekn110Cost'),
        'EKN120': document.getElementById('ekn120Cost'),
        'EKN214': document.getElementById('ekn214Cost')
    };
    
    const totalCostDisplay = document.getElementById('totalCost');
    
    // State management
    let selectedModule = '';
    let totalCost = 0;
    let uploadedFile = null;
    
    // Initialize form
    initializeForm();
    
    function initializeForm() {
        // Banking details per-field copy buttons
        setupBankingDetailsCopy();

        // Module selection handler
        moduleSelect.addEventListener('change', handleModuleChange);
        
        // Email validation
        emailInput.addEventListener('blur', validateEmail);
        emailInput.addEventListener('input', clearEmailError);
        
        // Phone validation
        phoneInput.addEventListener('input', formatPhone);
        
        // File upload handlers
        setupFileUpload();
        
        // Checkbox change handlers for cost calculation
        setupCostCalculation();
        
        // Disclaimer checkbox
        disclaimerCheckbox.addEventListener('change', updateSubmitButton);
        
        // Form submission
        form.addEventListener('submit', handleFormSubmission);
        
        // Initial state
        updateSubmitButton();
    }

    function setupBankingDetailsCopy() {
        document.querySelectorAll('.bank-copy-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const targetId = btn.dataset.copyTarget;
                const el = document.getElementById(targetId);
                if (!el) return;
                const text = (el.textContent || el.innerText || '').trim();

                try {
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        await navigator.clipboard.writeText(text);
                    } else {
                        const textarea = document.createElement('textarea');
                        textarea.value = text;
                        textarea.style.position = 'fixed';
                        textarea.style.opacity = '0';
                        document.body.appendChild(textarea);
                        textarea.select();
                        document.execCommand('copy');
                        document.body.removeChild(textarea);
                    }
                    const originalText = btn.textContent;
                    btn.classList.add('copied');
                    btn.textContent = 'Copied';
                    setTimeout(() => {
                        btn.classList.remove('copied');
                        btn.textContent = originalText;
                    }, 1200);
                } catch (err) {
                    console.error('Failed to copy', err);
                }
            });
        });
    }
    
    function handleModuleChange() {
        const selectedValue = moduleSelect.value;
        
        // Hide all sections first
        Object.values(moduleSections).forEach(section => {
            if (section) {
                section.style.display = 'none';
                section.classList.remove('active');
            }
        });
        
        // Clear all checkboxes when changing modules
        clearAllCheckboxes();
        
        // Show selected module section
        if (selectedValue && moduleSections[selectedValue]) {
            moduleSections[selectedValue].style.display = 'block';
            moduleSections[selectedValue].classList.add('active');
            selectedModule = selectedValue;
        } else {
            selectedModule = '';
        }
        
        // Update costs
        updateAllCosts();
        updateSubmitButton();
    }
    
    function clearAllCheckboxes() {
        const allCheckboxes = document.querySelectorAll('input[name="chapters"]');
        allCheckboxes.forEach(checkbox => {
            checkbox.checked = false;
        });
    }
    
    function setupCostCalculation() {
        const checkboxes = document.querySelectorAll('input[name="chapters"]');
        checkboxes.forEach(checkbox => {
            checkbox.addEventListener('change', updateAllCosts);
        });
    }
    
    function updateAllCosts() {
        let grandTotal = 0;
        
        // Update individual module costs
        Object.keys(moduleSections).forEach(module => {
            const moduleTotal = calculateModuleCost(module);
            if (costDisplays[module]) {
                costDisplays[module].textContent = `R ${moduleTotal}`;
            }
            grandTotal += moduleTotal;
        });
        
        // Update total cost
        totalCost = grandTotal;
        totalCostDisplay.textContent = `R ${totalCost}`;
        
        updateSubmitButton();
    }
    
    function calculateModuleCost(module) {
        const checkboxes = document.querySelectorAll(`input[name="chapters"][value^="${module}"]`);
        let total = 0;
        
        checkboxes.forEach(checkbox => {
            if (checkbox.checked) {
                total += parseInt(checkbox.dataset.cost) || 0;
            }
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
        const errorDiv = document.getElementById('emailError');
        hideError(errorDiv);
        emailInput.classList.remove('error');
    }
    
    function isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }
    
    function formatPhone() {
        let phone = phoneInput.value.replace(/\D/g, '');
        
        // Ensure it starts with 0 for South African numbers
        if (phone.length > 0 && !phone.startsWith('0')) {
            phone = '0' + phone;
        }
        
        // Format the number (0XX XXX XXXX)
        if (phone.length > 3 && phone.length <= 6) {
            phone = phone.slice(0, 3) + ' ' + phone.slice(3);
        } else if (phone.length > 6) {
            phone = phone.slice(0, 3) + ' ' + phone.slice(3, 6) + ' ' + phone.slice(6, 10);
        }
        
        phoneInput.value = phone;
    }
    
    function setupFileUpload() {
        // Click to upload
        fileUploadArea.addEventListener('click', () => fileInput.click());
        
        // File selection
        fileInput.addEventListener('change', handleFileSelection);
        
        // Drag and drop
        fileUploadArea.addEventListener('dragover', handleDragOver);
        fileUploadArea.addEventListener('dragleave', handleDragLeave);
        fileUploadArea.addEventListener('drop', handleFileDrop);
    }
    
    function handleFileSelection(event) {
        const file = event.target.files[0];
        if (file) {
            validateAndDisplayFile(file);
        }
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
            const file = files[0];
            fileInput.files = files; // Set the file input
            validateAndDisplayFile(file);
        }
    }
    
    function validateAndDisplayFile(file) {
        const errorDiv = document.getElementById('fileError');
        
        // Validate file type
        const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
        if (!allowedTypes.includes(file.type)) {
            showError(errorDiv, 'Invalid file type. Please upload a PDF, JPG, or PNG file.');
            clearFileInput();
            return;
        }
        
        // Validate file size (5MB limit)
        const maxSize = 5 * 1024 * 1024; // 5MB in bytes
        if (file.size > maxSize) {
            showError(errorDiv, 'File size too large. Please upload a file smaller than 5MB.');
            clearFileInput();
            return;
        }
        
        // File is valid
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
        const hasModule = selectedModule !== '';
        const hasChapters = getSelectedChapters().length > 0;
        const hasValidEmail = emailInput.value && validateEmail();
        const hasPhone = phoneInput.value.trim() !== '';
        const hasFirstName = document.getElementById('firstName').value.trim() !== '';
        const hasLastName = document.getElementById('lastName').value.trim() !== '';
        const hasFile = uploadedFile !== null;
        const hasAgreedToDisclaimer = disclaimerCheckbox.checked;
        const hasCost = totalCost > 0;
        
        const isValid = hasModule && hasChapters && hasValidEmail && hasPhone && 
                       hasFirstName && hasLastName && hasFile && hasAgreedToDisclaimer && hasCost;
        
        submitBtn.disabled = !isValid;
    }
    
    function getSelectedChapters() {
        const checkboxes = document.querySelectorAll('input[name="chapters"]:checked');
        return Array.from(checkboxes).map(cb => cb.value);
    }
    
    function handleFormSubmission(event) {
        event.preventDefault();
        
        // Final validation
        if (!validateForm()) {
            return;
        }
        
        // Show loading state
        submitBtn.disabled = true;
        document.getElementById('loadingSpinner').style.display = 'block';
        submitBtn.textContent = 'Processing...';
        
        // Prepare form data
        const formData = new FormData();
        
        // Add form fields
        formData.append('firstName', document.getElementById('firstName').value.trim());
        formData.append('lastName', document.getElementById('lastName').value.trim());
        formData.append('email', emailInput.value.trim());
        formData.append('phone', phoneInput.value.trim());
        formData.append('module', selectedModule);
        formData.append('chapters', JSON.stringify(getSelectedChapters()));
        formData.append('totalCost', totalCost);
        formData.append('proofOfPayment', uploadedFile);
        formData.append('timestamp', new Date().toISOString());
        
        // Submit to backend
        submitFormData(formData);
    }
    
    async function submitFormData(formData) {
        try {
            const response = await fetch('/submit', {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const result = await response.json();
                showSuccessMessage();
            } else {
                throw new Error('Submission failed');
            }
        } catch (error) {
            console.error('Submission error:', error);
            showErrorMessage();
        } finally {
            // Reset loading state
            submitBtn.disabled = false;
            document.getElementById('loadingSpinner').style.display = 'none';
            submitBtn.textContent = 'Submit Request';
        }
    }
    
    function validateForm() {
        let isValid = true;
        
        // Validate all required fields
        const requiredFields = [
            { id: 'firstName', message: 'First name is required' },
            { id: 'lastName', message: 'Last name is required' },
            { id: 'email', message: 'Email is required' },
            { id: 'phone', message: 'Phone number is required' }
        ];
        
        requiredFields.forEach(field => {
            const element = document.getElementById(field.id);
            if (!element.value.trim()) {
                element.classList.add('error');
                isValid = false;
            } else {
                element.classList.remove('error');
            }
        });
        
        // Validate email
        if (!validateEmail()) {
            isValid = false;
        }
        
        // Validate module and chapters
        if (!selectedModule) {
            moduleSelect.classList.add('error');
            isValid = false;
        }
        
        if (getSelectedChapters().length === 0) {
            alert('Please select at least one chapter.');
            isValid = false;
        }
        
        // Validate file
        if (!uploadedFile) {
            showError(document.getElementById('fileError'), 'Proof of payment is required.');
            isValid = false;
        }
        
        // Validate disclaimer
        if (!disclaimerCheckbox.checked) {
            alert('Please read and agree to the disclaimer.');
            isValid = false;
        }
        
        return isValid;
    }
    
    function showSuccessMessage() {
        const successHtml = `
            <div style="text-align: center; padding: 40px; background: #d4edda; border-radius: 12px; margin: 20px 0;">
                <h2 style="color: #155724; margin-bottom: 15px;">✅ Request Submitted Successfully!</h2>
                <p style="color: #155724; font-size: 1.1rem;">
                    Thank you for your request! We've received your proof of payment and will process your order shortly.
                    You'll receive access to your study materials via Google Drive once approved.
                </p>
                <p style="color: #155724; margin-top: 15px;">
                    <strong>Total Cost:</strong> R ${totalCost}<br>
                    <strong>Module:</strong> ${selectedModule}<br>
                    <strong>Chapters:</strong> ${getSelectedChapters().length} selected
                </p>
            </div>
        `;
        
        form.innerHTML = successHtml;
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
    
    // Add input listeners for real-time validation
    ['firstName', 'lastName', 'email', 'phone'].forEach(fieldId => {
        const field = document.getElementById(fieldId);
        field.addEventListener('input', updateSubmitButton);
        field.addEventListener('blur', updateSubmitButton);
    });
});

