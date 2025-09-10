from django import forms

class ShortestPathForm(forms.Form):
    floor = forms.IntegerField()
    target = forms.CharField(required=False)
    sources = forms.CharField(required=False)

    def sources_list(self):
        s = self.cleaned_data.get('sources')
        if not s:
            return []
        return [x.strip() for x in s.split(',') if x.strip()]