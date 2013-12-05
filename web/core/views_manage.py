import uuid
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import User as AuthUser
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse, reverse_lazy

# Create your views here.
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect
from django.utils.text import slugify
from django.views.generic import FormView

from django import forms
from core.models import Organization, User, customer_group, Installation, UserTag, Tag
from web.baseviews import PageTitleMixin

from django.utils.translation import ugettext_lazy as _

class NewUserAndOrganizationForm(forms.Form):
    email = forms.EmailField(required=True, label="Din email")
    organization_name = forms.CharField(required=True, label="Organisationsnamn", max_length=512)

    def clean_organization_name(self):
        if len(Organization.objects.filter(slug=slugify(self.cleaned_data["organization_name"]))) > 0:
            raise ValidationError(
                _('En organisation med namnet %(value)s finns redan'),
                code='invalid',
                params={'value': self.cleaned_data["organization_name"]},
                )
        return self.cleaned_data["organization_name"]

def _createNewUser(email, org):
    with transaction.atomic():
        auth_user = AuthUser.objects.create_user(email,
                                                 email, uuid.uuid1().hex)

        user = User.objects.create(name="", email=email,
                                   organization = org, auth_user = auth_user, owner=True)
        Installation.objects.create(user = user)
        auth_user = authenticate(auth_user=auth_user)
        auth_user.groups.add(customer_group)
        auth_user.save()
    return user, auth_user

class RegisterView(PageTitleMixin, FormView):
    title = "Starta docloud!"
    template_name = 'manage/register.html'
    form_class = NewUserAndOrganizationForm
    success_url = None

    def form_valid(self, form):
        with transaction.atomic():
            org = Organization.objects.create(name=form.cleaned_data["organization_name"])
            user, auth_user = _createNewUser(form.cleaned_data["email"], org)
            logout(self.request)
            login(self.request, auth_user)
            self.success_url = reverse("manage:organization", args=(org.slug,)) + "?token"
        return super().form_valid(form)

class ActivatedFormMixin(forms.Form):
    form_id = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, "form_id_str"):
            raise AttributeError("form_id_str is required for ActivatedFormMixin siblings!")
        self.fields["form_id"].initial = self.form_id_str

    def is_active(self):
        return self.data.get("form_id") == self.form_id_str

class NewUserForm(ActivatedFormMixin, forms.Form):
    form_id_str = "new_user_form"
    email = forms.EmailField()

    def clean_email(self):
        if len(User.objects.filter(email = self.cleaned_data["email"])) > 0:
            raise ValidationError(
                _('En användare med emailen %(value)s finns redan'),
                code='invalid',
                params={'value': self.cleaned_data["email"]},
                )
        return self.cleaned_data["email"]

class NewTagForm(ActivatedFormMixin, forms.Form):
    name = forms.CharField(max_length=512, label="Ny tagg", required=True)
    form_id_str = "new_tag_form"

    def __init__(self, *args, request = None, **kwargs):
        if request is None:
            raise ValueError("Request can not be None!")
        self.request = request
        super().__init__(*args, **kwargs)

    def clean_name(self):
        if len(Tag.objects.filter(organization = self.request.loggedin().organization, name = self.cleaned_data["name"])) > 0:
            raise ValidationError(
                _('En tagg med namnet %(value)s finns redan'),
                code='invalid',
                params={'value': self.cleaned_data["name"]},
                )
        return self.cleaned_data["name"]

class AddUserForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.all(), empty_label="Välj användare")
    add_user_tag_id = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, tag_id = None, **kwargs):
        if tag_id is None:
            raise ValueError("tag_id can not be None!")
        super().__init__(*args, **kwargs)
        self.fields["add_user_tag_id"].initial = str(tag_id)

def _lazyAddUserForm(request, usertags):
    for usertag in usertags:
        def lazyCrateUserForm(usertag):
            def curry():
                add_user_form = AddUserForm(tag_id=usertag.tag.id)
                add_user_form.fields['user'].queryset = add_user_form.fields['user'].queryset. \
                    filter(organization = request.loggedin().organization).exclude(usertag__tag = usertag.tag)
                return add_user_form
            return curry
        setattr(usertag, "add_user_form", lazyCrateUserForm(usertag))
        yield usertag

def _getLazyTagCreatorUserTags(request):
    usertags = (UserTag(tag=tag, user=request.loggedin(), owns_tag = True)
                for tag in request.loggedin().organization.tags.all())
    return _lazyAddUserForm(request, usertags)

@permission_required('core.is_customer', login_url="/inloggning/")
def delete_tag(request, org_slug, tag_id):
    """
    Delete the tag pointed to by tag_id redirecting to manage:organization when done
    """
    org = request.loggedin().organization
    if org_slug != org.slug:
        raise Http404()
    if request.loggedin().owner or request.loggedin().tag_creator:
        try:
            tag = Tag.objects.get(pk=tag_id)
            if tag.organization.id == request.loggedin().organization.id:
                tag.delete()
        except Tag.DoesNotExist:
            pass
    return redirect(reverse("manage:organization", args=(org.slug,)))

@permission_required('core.is_customer', login_url="/inloggning/")
def delete_usertag(request, org_slug, tag_id, user_id):
    """
    Delete the usertag pointed to by tag_id + user_id, redirecting to manage:organization when done
    """
    org = request.loggedin().organization
    if org_slug != org.slug:
        raise Http404()
    if request.loggedin().owner or request.loggedin().tag_creator:
        try:
            usertag = UserTag.objects.get(tag__id = tag_id, user__id = user_id)
            if usertag.tag.organization == request.loggedin().organization:
                allowed = True
                if not request.loggedin().owner and not request.loggedin().tag_creator:
                    loggedin_usertag = usertag.tag.usertag_set.get(user = request.loggedin())
                    if not loggedin_usertag.owns_tag:
                        allowed = False
                if allowed:
                    usertag.delete()
        except UserTag.DoesNotExist:
            pass
    return redirect(reverse("manage:organization", args=(org.slug,)))

def _processNewUserForm(request):
    """
    Return a NewUserForm if the user is owner, and create a new user if POST
    Returns form=None if not owner and user=False if no user created
    Returns (form, user)
    """
    if request.loggedin().owner:
        if request.method == "POST":
            new_user_form = NewUserForm(request.POST)
            if new_user_form.is_active():
                if new_user_form.is_valid():
                    user, auth_user = _createNewUser(new_user_form.cleaned_data["email"], request.loggedin().organization)
                    return NewUserForm(), user
                else:
                    return new_user_form, False
            else:
                return NewUserForm(), False
        else:
            return NewUserForm(), False
    return None, False

def _processNewTagForm(request):
    """
    Return a NewTagForm if the user is admin, and create a Tag if POST
    Returns None if not admin
    """
    if request.loggedin().owner or request.loggedin().tag_creator:
        if request.method == "POST":
            new_tag_form = NewTagForm(request.POST, request = request)
            if new_tag_form.is_active():
                if new_tag_form.is_valid():
                    with transaction.atomic():
                        new_tag = Tag.objects.create(organization = request.loggedin().organization,
                                                     name = new_tag_form.cleaned_data["name"])
                        UserTag.objects.create(user = request.loggedin(), tag = new_tag, owns_tag = True)
                else:
                    return new_tag_form
        else:
            return NewTagForm(request=request)
    return None

@permission_required('core.is_customer', login_url="/inloggning/")
def organization(request, org_slug):
    """
    Serve a page listing all tags the user is subscribed to (or all if admin), along with other users subscribed
    to those tags. Show create/delete-functions for Tags, Users and UserTags if the loggedin is admin
    """
    # "Return" 404 if the url doesn't match the logged in users organization
    org = request.loggedin().organization
    if org_slug != org.slug:
        raise Http404()

    # If the user was redirected from the registration page, set "token" to the first installation uuid for downloading
    # TODO: This is temporary since we don't have a client yet
    token = False
    if request.GET.get("token", None) is not None:
        installations = list(request.loggedin().installations.all())
        if len(installations) == 1:
            token = installations[0].uuid

    # Create form for creating new user if the loggedin is the owner of the organization
    # Handles POST to the form and returns the user if created
    new_user_form, new_user_created = _processNewUserForm(request)

    # Create form for creating new tags if the loggedin is owner or tag_creator
    # Handles POST to the form and creates new tags
    new_tag_form = _processNewTagForm(request)

    if request.loggedin().owner or request.loggedin().tag_creator:
        # Since this user is admin, it should be able to see all tags, including ones where it isn't subscribed
        # Create a lazy list of UserTags based on all tags available for the organization, and all marked as "owned"
        usertags = _getLazyTagCreatorUserTags(request)

        # If the user has the ability to add users to tags, we check if a valid AddUserForm has been submitted
        # Then validate it against the list of users not already added to that tag and then add the user
        if request.method == "POST" and request.POST.get("add_user_tag_id") is not None:
            try:
                tag_id = int(request.POST["add_user_tag_id"])
                tag = Tag.objects.get(pk=tag_id)
                add_user_form = AddUserForm(request.POST, tag_id=tag.id)
                add_user_form.fields['user'].queryset = add_user_form.fields['user'].queryset. \
                    filter(organization = request.loggedin().organization).exclude(usertag__tag = tag)
                if add_user_form.is_valid():
                    UserTag.objects.create(user = add_user_form.cleaned_data["user"], tag = tag, owns_tag = False)
            except Tag.DoesNotExist:
                pass
    else:
        # Fetch all usertags that this user subscribes to
        usertags = request.loggedin().usertag_set.all()

    return render(request, "manage/organization.html", {"TITLE": org.name,
                                                        "org":org,
                                                        "usertags":usertags,
                                                        "token": token,
                                                        "new_tag_form":new_tag_form,
                                                        "new_user_form":new_user_form,
                                                        "new_user_created":new_user_created})

def link_download(request, token):
    """
    Return a docloud.url file pointing to the loginpage using token
    """
    response_str = """[InternetShortcut]
URL=%s
""" % request.build_absolute_uri(reverse("manage:token_login", args=(token,)))
    response = HttpResponse(response_str, content_type="application/octet-stream")
    response['Content-Disposition'] = 'attachment; filename="docloud.url"'
    return response

def token_login(request, token):
    """
    Login a user based on a token
    Relies on core.auth.TokenLoginBackend
    """
    logout(request)
    auth_user = authenticate(token = token)
    login(request, auth_user)
    if auth_user:
        return redirect(reverse("manage:organization", args=(auth_user.docloud_users.get().organization.slug,)))
    else:
        return render(request, "manage/login_failed.html", {"TITLE":"Inloggningen misslyckades"})