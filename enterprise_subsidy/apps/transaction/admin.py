""" Top level admin configuration for the subsidy service. """

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import re_path, reverse
from djangoql.admin import DjangoQLSearchMixin
from openedx_ledger.admin import TransactionAdmin as BaseTransactionAdmin
from openedx_ledger.models import Transaction

from enterprise_subsidy.apps.transaction import views

admin.site.unregister(Transaction)


@admin.register(Transaction)
class TransactionAdmin(DjangoQLSearchMixin, BaseTransactionAdmin):
    """
    Subsidy specific implimentation of the Admin configuration for the Transaction model.
    Includes a custom action for unenrolling learners from the platform enrollment associated with a transaction
    without interacting/reversing with the object.
    """
    class Meta:
        model = Transaction
        fields = '__all__'

    change_actions = BaseTransactionAdmin.change_actions + ('unenroll',)

    # From https://github.com/ivelum/djangoql#using-djangoql-with-the-standard-django-admin-search:
    # "DjangoQL will recognize if you have defined search_fields in your ModelAdmin class,
    # and doing so will allow you to choose between an advanced search with
    # DjangoQL and a standard Django search (as specified by search fields)"
    # TODO:
    # djangoql it doesn't seem to take search_fields from the parent class into account
    # when doing this check, so we redefine them here for now.
    search_fields = (
        'content_key',
        'lms_user_id',
        'uuid',
        'external_reference__external_reference_id',
        'subsidy_access_policy_uuid',
    )

    def unenroll(self, request, obj):
        """
        Redirect to the unenroll view.
        """
        # url names coming from get_urls are prefixed with 'admin' namespace
        unenroll_url = reverse("admin:unenroll", args=(obj.uuid,))
        return HttpResponseRedirect(unenroll_url)

    unenroll.label = "Unenroll"
    unenroll.short_description = (
        "Unenroll the learner from the platform representation of the course."
    )

    def get_urls(self):
        """
        Returns the additional urls used by DjangoObjectActions.
        """
        custom_urls = [
            re_path(
                r"^([^/]+)/unenroll$",
                self.admin_site.admin_view(views.UnenrollLearnersView.as_view()),
                name="unenroll"
            ),
        ]
        return custom_urls + super().get_urls()
