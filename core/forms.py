from django import forms

from .models import AmbulanceRequest


class AmbulanceRequestForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput, label="Leave blank")

    class Meta:
        model = AmbulanceRequest
        fields = ["service_type", "patient_name", "phone", "pickup_location", "destination", "details"]
        widgets = {
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "pickup_location": forms.TextInput(attrs={"autocomplete": "street-address"}),
            "details": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "patient_name": "Patient or caller name",
            "pickup_location": "Pickup location",
            "destination": "Destination (optional)",
            "details": "Important details (optional)",
        }

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Invalid submission.")
        return ""
