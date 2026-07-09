from rest_framework.routers import DefaultRouter

from .views import BusinessViewSet, CategoryViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("businesses", BusinessViewSet, basename="business")

urlpatterns = router.urls
