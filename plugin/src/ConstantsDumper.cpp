#include "clang/Frontend/FrontendPluginRegistry.h"
#include "clang/AST/AST.h"
#include "clang/AST/ASTConsumer.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include <iostream>

using namespace std;
using namespace clang;

#if __cplusplus < 201402L
using llvm::make_unique;
#endif

namespace
{
class ConstantsDumperClassVisitor : public RecursiveASTVisitor<ConstantsDumperClassVisitor>
{
public:
    bool VisitEnumDecl(EnumDecl *decl)
    {
        cout << "enum " << decl->getQualifiedNameAsString() << " {" << endl;
        auto iter = decl->enumerator_begin();

        while (iter != decl->enumerator_end())
        {
            auto enum_constant_decl = iter++;
            std::cout << enum_constant_decl->getQualifiedNameAsString() << "=";
            auto value = enum_constant_decl->getInitVal();
            std::cout << value.getExtValue();

            cout << "," << endl;
        }
        cout << "}" << endl;

        return true;
    }

    bool VisitVarDecl(VarDecl *decl)
    {
        // Check only fundamental types
        if (!decl->getType()->isFundamentalType())
        {
            return true;
        }

        // This is in order to exclude function parameters
        if (decl->isLocalVarDeclOrParm() && !decl->isLocalVarDecl())
        {
            return true;
        }

        // Make sure there is an initialization for the variable
        if (!decl->hasInit())
        {
            return true;
        }

        // If the init expression is function call, we want to make sure that it's constexpr
        /*CallExpr* func_call = dyn_cast<CallExpr>(decl->getInit());
            if (func_call != nullptr)
            {
                printf("CallExpr!\n");
                auto func_decl = func_call->getDirectCallee();
                if (func_decl != nullptr)
                {
                    if (!func_decl->isConstexpr())
                    {
                        return true;
                    }
                }
            }*/
        // else, it's probably ok.... if more types give us problems we will patch them too

        if (decl->isConstexpr() || (decl->checkInitIsICE() && decl->isUsableInConstantExpressions(*context)))
        {
            if (decl->getEvaluatedValue() == nullptr)
            {
                return true;
            }

            cout << decl->getQualifiedNameAsString() << "=" << decl->getEvaluatedValue()->getInt().getExtValue() << endl;
        }

        return true;
    }

    void setContext(ASTContext &context)
    {
        this->context = &context;
    }

private:
    ASTContext *context;
};

class ConstantsDumperConsumer : public ASTConsumer
{
public:
    void HandleTranslationUnit(ASTContext &context)
    {
        visitor.setContext(context);
        visitor.TraverseDecl(context.getTranslationUnitDecl());
    }

private:
    ConstantsDumperClassVisitor visitor;
};

class ConstantsDumperASTAction : public PluginASTAction
{
public:
    virtual std::unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &Compiler,
                                                           llvm::StringRef InFile)
    {
        return make_unique<ConstantsDumperConsumer>();
    }

    bool ParseArgs(const CompilerInstance &CI,
                   const std::vector<std::string> &args)
    {
        return true;
    }
};
} // namespace

static clang::FrontendPluginRegistry::Add<ConstantsDumperASTAction> X("ConstantsDumper", "Dumps all constants and enums from the code");
